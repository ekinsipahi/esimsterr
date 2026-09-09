"""Payment orchestration: start a payment, settle it, release the order for fulfilment.

`settle_payment` is the single door through which an order becomes PAID, so the
Stripe webhook, the crypto IPN and a manual admin settlement all behave identically
and are all idempotent.
"""
from __future__ import annotations

import logging
from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import transaction
from django.urls import reverse

from apps.orders.models import Order

from . import nowpayments, stripe_client
from .models import Payment

log = logging.getLogger(__name__)


class PaymentError(Exception):
    pass


def _payment_by_reference(reference) -> Payment | None:
    """Look a Payment up by the reference we handed the provider.

    The reference is our Payment UUID. A malformed value would make a UUID field
    lookup raise, so anything unparseable resolves to "unknown payment" instead.
    """
    if not reference:
        return None
    try:
        return Payment.objects.filter(pk=str(reference)).first()
    except (ValidationError, ValueError):
        return None


def _abs(request, path):
    if request is not None:
        return request.build_absolute_uri(path)
    return f"{settings.SITE_URL}{path}"


def start_payment(order: Order, method: str, request=None) -> str:
    """Create the provider checkout and return the URL to redirect the customer to."""
    method = (method or "").lower()
    if method not in ("stripe", "crypto", "nowpayments"):
        raise PaymentError("Choose a payment method.")

    success_url = _abs(request, reverse("order_detail", kwargs={"ref": order.ref}))
    cancel_url = _abs(request, reverse("checkout", kwargs={"plan_id": order.plan_id})) if order.plan_id else success_url
    description = f"{settings.SITE_NAME} — {order.plan_title}"

    if method == "stripe":
        if not stripe_client.configured():
            raise PaymentError("Card payments are not available right now. Please pay with crypto.")
        payment = Payment.objects.create(
            order=order, user=order.user, provider=Payment.Provider.STRIPE,
            amount_usd=order.amount_usd,
        )
        # Stripe appends the session id so the return page can settle immediately
        # even if the webhook is a beat behind.
        session = stripe_client.create_checkout_session(
            amount_usd=order.amount_usd,
            reference=str(payment.id),
            description=description,
            success_url=success_url + "?paid=1&session_id={CHECKOUT_SESSION_ID}",
            cancel_url=cancel_url,
            customer_email=order.email,
        )
        payment.provider_session_id = session.get("id", "")
        payment.checkout_url = session.get("url", "")
        payment.status = Payment.Status.WAITING
        payment.raw = {"session": session.get("id", "")}
        payment.save(update_fields=["provider_session_id", "checkout_url", "status", "raw"])
        if not payment.checkout_url:
            raise PaymentError("Stripe did not return a checkout URL.")
        return payment.checkout_url

    if not nowpayments.configured():
        raise PaymentError("Crypto payments are not available right now.")
    payment = Payment.objects.create(
        order=order, user=order.user, provider=Payment.Provider.NOWPAYMENTS,
        amount_usd=order.amount_usd,
    )
    invoice = nowpayments.create_invoice(
        amount_usd=order.amount_usd,
        reference=str(payment.id),
        description=description,
        success_url=success_url + "?paid=1",
        cancel_url=cancel_url,
        ipn_url=_abs(request, reverse("nowpayments_ipn")),
    )
    payment.provider_payment_id = str(invoice.get("id", ""))
    payment.checkout_url = invoice.get("invoice_url", "")
    payment.status = Payment.Status.WAITING
    payment.raw = invoice
    payment.save(update_fields=["provider_payment_id", "checkout_url", "status", "raw"])
    if not payment.checkout_url:
        raise PaymentError("The crypto payment provider did not return an invoice URL.")
    return payment.checkout_url


@transaction.atomic
def settle_payment(payment_id, *, paid_amount_usd=None, provider_payment_id="", raw=None) -> Payment:
    """Mark a payment paid and release its order for provisioning. Idempotent.

    An underpaid crypto invoice is recorded but never released: the customer paid
    less than the plan costs us, so nothing is provisioned until it is topped up.
    """
    payment = Payment.objects.select_for_update().get(pk=payment_id)
    if provider_payment_id:
        payment.provider_payment_id = provider_payment_id
    if raw:
        payment.raw = {**(payment.raw or {}), **raw}

    if paid_amount_usd is not None:
        payment.paid_amount_usd = Decimal(str(paid_amount_usd)).quantize(Decimal("0.01"))

    if payment.settled:
        payment.save()
        return payment

    arrived = payment.paid_amount_usd if payment.paid_amount_usd is not None else payment.amount_usd
    # Crypto conversion wobble: accept 2% under the invoice as fully paid.
    if arrived < payment.amount_usd * Decimal("0.98"):
        payment.status = Payment.Status.PARTIAL
        payment.save()
        log.warning("Underpaid payment %s: $%s of $%s", payment.id, arrived, payment.amount_usd)
        from apps.accounts.emails import notify_admin
        notify_admin(
            f"Underpaid order {payment.order.ref}",
            [f"Invoice: ${payment.amount_usd}", f"Received: ${arrived}",
             f"Customer: {payment.order.email}", "Nothing was provisioned."],
        )
        return payment

    payment.status = Payment.Status.PAID
    payment.settled = True
    payment.save()

    order = payment.order
    order.mark_paid()

    def _provision():
        from apps.orders.services import fulfill_order
        try:
            fulfill_order(order.pk)
        except Exception:  # noqa: BLE001
            # The order stays PAID with the error recorded; the cron sweeper and
            # the admin action both retry it. The customer's money is not lost.
            log.exception("post-payment fulfilment failed for %s", order.ref)

    transaction.on_commit(_provision)
    return payment


def settle_stripe_session(session: dict) -> Payment | None:
    """Shared by the webhook and the success-page fallback."""
    reference = session.get("client_reference_id") or (session.get("metadata") or {}).get("reference")
    if not reference:
        return None
    payment = _payment_by_reference(reference)
    if payment is None:
        log.warning("Stripe session for unknown reference %r", reference)
        return None
    total = session.get("amount_total")
    paid = Decimal(str(total)) / 100 if total is not None else None
    return settle_payment(
        payment.pk,
        paid_amount_usd=paid,
        provider_payment_id=str(session.get("payment_intent") or session.get("id") or ""),
        raw={"stripe_status": session.get("payment_status")},
    )


NOWPAY_PAID = {"finished", "confirmed"}
NOWPAY_DEAD = {"failed", "expired", "refunded"}


def process_nowpayments_ipn(payload: dict) -> None:
    reference = payload.get("order_id") or ""
    payment = _payment_by_reference(reference)
    if payment is None:
        log.warning("NOWPayments IPN for unknown reference %r", reference)
        return
    status = (payload.get("payment_status") or "").lower()
    provider_id = str(payload.get("payment_id") or "")

    if status in NOWPAY_PAID:
        settle_payment(payment.pk, paid_amount_usd=_nowpay_usd(payload, payment.amount_usd),
                       provider_payment_id=provider_id, raw=payload)
        return

    payment.provider_payment_id = provider_id or payment.provider_payment_id
    payment.pay_currency = payload.get("pay_currency") or payment.pay_currency
    payment.raw = payload
    if status in NOWPAY_DEAD:
        payment.status = Payment.Status.EXPIRED if status == "expired" else Payment.Status.FAILED
        if payment.order.status == Order.Status.PENDING:
            payment.order.status = Order.Status.CANCELLED
            payment.order.save(update_fields=["status"])
    elif status == "confirming":
        payment.status = Payment.Status.CONFIRMING
    elif status == "partially_paid":
        payment.status = Payment.Status.PARTIAL
    payment.save()


def _nowpay_usd(payload: dict, invoice_usd) -> Decimal:
    """USD value of what actually arrived. Unknown resolves to 0 — 'unknown' must
    never be treated as 'paid in full'."""
    fiat = payload.get("actually_paid_at_fiat")
    try:
        v = Decimal(str(fiat))
        if v > 0:
            return v.quantize(Decimal("0.01"))
    except Exception:  # noqa: BLE001
        pass
    if payload.get("parent_payment_id"):
        return Decimal("0")
    try:
        pay = Decimal(str(payload.get("pay_amount") or 0))
        actually = Decimal(str(payload.get("actually_paid") or 0))
        if pay > 0 and actually > 0:
            return (Decimal(invoice_usd) * actually / pay).quantize(Decimal("0.01"))
    except Exception:  # noqa: BLE001
        pass
    return Decimal("0")
