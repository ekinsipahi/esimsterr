"""Order fulfilment: turn a paid order into a live eSIM via the provider API.

Design rules:
  * Provisioning only ever runs for a PAID order and is idempotent — a webhook
    retry, a manual admin retry and the cron sweeper all funnel through
    `fulfill_order`, which no-ops once the order is COMPLETED.
  * A provider failure never loses the sale: the order stays PAID with the error
    recorded, the operator gets an email, and `retry_failed` picks it back up.
  * We never charge the customer inside this module — money is settled in
    apps.payments before fulfilment starts.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone as dt_timezone

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from apps.accounts.emails import send_esim_ready
from apps.accounts.notifications import failure_alert, sale_alert
from apps.providers.yesim import YesimError, client

from .models import Esim, Order

log = logging.getLogger(__name__)


def guest_checkout_allowed() -> bool:
    """Whether somebody may buy without an account right now.

    Reads the remote switch as well as the setting, which nothing did before:
    `guest_checkout` was published to the app and enforced nowhere, so turning
    it off during an incident hid a button and left the website selling. A
    switch that stops nothing is worse than no switch -- somebody flips it and
    believes the problem is contained.

    ANDed rather than either-or, so the switch can only ever close. An operator
    cannot turn guest buying back on against the setting, and a config or
    database failure cannot close the till by accident.
    """
    if not getattr(settings, "GUEST_CHECKOUT", False):
        return False
    try:
        from apps.common.models import RemoteConfig

        return RemoteConfig.current().guest_checkout
    except Exception:  # noqa: BLE001 - a config read must not stop a purchase
        return True


def _parse_dt(value):
    """Provider timestamps are 'YYYY-MM-DD HH:MM:SS' in UTC."""
    if not value:
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d %H:%M:%S").replace(tzinfo=dt_timezone.utc)
    except (ValueError, TypeError):
        return None


def _dec(value):
    if value in (None, ""):
        return None
    try:
        return round(float(value), 2)
    except (TypeError, ValueError):
        return None


def apply_sim_info(esim: Esim, info: dict, *, save=True) -> Esim:
    """Copy a /sim_info or /new_esim payload onto our row."""
    esim.provider_esim_id = str(info.get("id") or esim.provider_esim_id or "")
    esim.provider_user_id = str(info.get("user_id") or esim.provider_user_id or "")
    esim.lpa_code = info.get("qrcode") or esim.lpa_code
    esim.ios_tap_link = info.get("ios_tap_link") or esim.ios_tap_link
    esim.esim_passport_url = info.get("esim_passport") or esim.esim_passport_url
    esim.imsi = str(info.get("imsi") or esim.imsi or "")
    esim.msisdn = str(info.get("msisdn") or esim.msisdn or "")
    if info.get("status_qr"):
        esim.status_qr = info["status_qr"]
    if info.get("active_plan_id"):
        esim.active_plan_provider_id = str(info["active_plan_id"])
    esim.plan_activated_at = _parse_dt(info.get("plan_activated_at")) or esim.plan_activated_at
    esim.plan_expires_at = _parse_dt(info.get("plan_expired_at")) or esim.plan_expires_at
    esim.data_package_mb = _dec(info.get("data_package_mb")) or esim.data_package_mb
    esim.data_used_mb = _dec(info.get("data_used_mb")) if info.get("data_used_mb") is not None else esim.data_used_mb
    esim.data_left_mb = _dec(info.get("data_left_mb")) if info.get("data_left_mb") is not None else esim.data_left_mb
    # Unlimited plans report only data_used_mb — no package/left figures.
    if info.get("data_package_mb") is None and info.get("data_used_mb") is not None:
        esim.is_unlimited = True
    if info.get("networkinfo"):
        esim.network_info = info["networkinfo"]
    esim.is_deleted = str(info.get("is_deleted") or "0") == "1"
    esim.last_synced_at = timezone.now()
    if save:
        esim.save()
    return esim


def ensure_provider_user(user) -> str:
    """Lazily create the customer's account on the provider so their eSIMs group together."""
    if user is None:
        return ""
    if user.yesim_user_id:
        return user.yesim_user_id
    try:
        data = client().new_user(user.email)
        uid = str(data.get("user_id") or "")
    except YesimError as e:
        # 'already exists' or a transient failure — an eSIM without a provider
        # user is still perfectly usable, so never block the sale on this.
        log.warning("provider user creation failed for %s: %s", user.email, e)
        return ""
    if uid:
        user.yesim_user_id = uid
        user.save(update_fields=["yesim_user_id"])
    return uid


@transaction.atomic
def fulfill_order(order_id) -> Order:
    """Provision (or top up) the eSIM for a paid order. Idempotent and lock-guarded."""
    order = Order.objects.select_for_update().get(pk=order_id)
    if order.status == Order.Status.COMPLETED:
        return order
    if order.status != Order.Status.PAID:
        raise ValueError(f"Order {order.ref} is {order.status}, refusing to fulfil")

    order.fulfillment_attempts += 1
    order.save(update_fields=["fulfillment_attempts"])

    c = client()
    try:
        if order.kind == Order.Kind.TOPUP:
            esim = _topup(c, order)
        else:
            esim = _provision_new(c, order)
    except YesimError as e:
        order.fulfillment_error = str(e)[:2000]
        order.save(update_fields=["fulfillment_error"])
        log.exception("fulfilment failed for %s", order.ref)
        failure_alert(order, str(e))
        raise

    order.status = Order.Status.COMPLETED
    order.completed_at = timezone.now()
    order.fulfillment_error = ""
    order.save(update_fields=["status", "completed_at", "fulfillment_error"])

    def _after_commit():
        send_esim_ready(order, esim)
        # A test order still delivers a real eSIM, but it is not a sale. Letting
        # it into the alerts would put fictional money in the daily total, and
        # an operator who stops trusting those numbers stops reading them --
        # and then misses a real failure.
        if not order.is_test:
            sale_alert(order, esim)
        else:
            log.warning("TEST ORDER %s provisioned; no sale alert sent", order.ref)

    transaction.on_commit(_after_commit)
    return order


def _provision_new(c, order: Order) -> Esim:
    """Issue a brand-new eSIM with the plan already attached (single provider call)."""
    provider_user_id = ensure_provider_user(order.user)
    info = c.new_esim(plan_id=order.plan_provider_id, user_id=provider_user_id or None)
    iccid = str(info.get("iccid") or "")
    if not iccid:
        raise YesimError(f"Provider returned no ICCID: {str(info)[:200]}")

    # A gift belongs to the person travelling with it. Filing it under the buyer
    # would put somebody else's QR code, usage and remaining data on the buyer's
    # dashboard, and leave the recipient with an email and no way to manage what
    # they were given. It stays unowned until they verify the address.
    esim, created = Esim.objects.get_or_create(
        iccid=iccid,
        defaults={
            "user": (None if order.is_gift else order.user),
            "email": order.delivery_email,
            "order": order,
            "apn": (order.plan.apn if order.plan else ""),
        },
    )
    if not created and esim.order_id and esim.order_id != order.id:
        # The provider handed back an ICCID that already belongs to another
        # order. Never silently complete this order against someone else's eSIM:
        # stop, leave the order PAID, and let the operator sort it out.
        raise YesimError(
            f"Provider returned ICCID {iccid}, already assigned to order "
            f"{esim.order.ref}. Order {order.ref} was NOT provisioned."
        )
    if not order.is_gift:
        esim.user = esim.user or order.user
    esim.email = esim.email or order.delivery_email
    esim.order = esim.order or order
    esim.plan_title = order.plan_title
    esim.is_unlimited = bool(order.plan and order.plan.is_unlimited)
    esim.active_plan_provider_id = order.plan_provider_id
    apply_sim_info(esim, info)
    return esim


def _topup(c, order: Order) -> Esim:
    """Attach another plan to an eSIM the customer already holds."""
    esim = order.target_esim
    if esim is None:
        raise YesimError("Top-up order has no target eSIM")
    c.add_plan(esim.iccid, order.plan_provider_id, payment_id=order.ref)
    esim.plan_title = order.plan_title
    esim.is_unlimited = bool(order.plan and order.plan.is_unlimited)
    esim.active_plan_provider_id = order.plan_provider_id
    try:
        apply_sim_info(esim, c.sim_info(esim.iccid))
    except YesimError:
        esim.save()  # the plan is on; the refresh can wait for the cron
    return esim


def sync_esim(esim: Esim) -> Esim:
    """Refresh usage/status for one eSIM from the provider."""
    return apply_sim_info(esim, client().sim_info(esim.iccid))


def retry_failed(limit=20):
    """Sweeper for paid-but-unprovisioned orders (provider hiccup, empty balance...)."""
    stuck = Order.objects.filter(status=Order.Status.PAID).order_by("paid_at")[:limit]
    ok = failed = 0
    for order in stuck:
        try:
            fulfill_order(order.pk)
            ok += 1
        except Exception:  # noqa: BLE001
            failed += 1
    return ok, failed
