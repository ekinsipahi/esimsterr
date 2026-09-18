"""Subscription pricing, Stripe event handling and cycle fulfilment.

The contract with the rest of the codebase: a subscription never provisions
anything by itself. Each paid cycle creates a real orders.Order and hands it to
apps.orders.services.fulfill_order — the same path a one-off purchase takes — so
there is exactly one fulfilment implementation, one margin calculation and one
order history for the customer to read.

Cycle money is mirrored into apps.payments.Payment as well. Stripe Billing
collects it directly, so apps.payments.services never sees a subscription charge
and nothing else would write that row: without it the ledger would report zero
revenue for every subscriber and never reconcile against Stripe.
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta, timezone as dt_timezone
from decimal import ROUND_DOWN, ROUND_HALF_UP, Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from apps.accounts.emails import notify_admin, send_email_bg
from apps.catalog.pricing import charm, cost_to_usd
from apps.orders.models import Esim, Order
from apps.payments.models import Payment
from apps.wallet.models import InsufficientBalance, Wallet

from .models import Subscription, SubscriptionCycle
from .stripe_sub import SubscriptionError, retrieve_subscription

log = logging.getLogger(__name__)

CENT = Decimal("0.01")

# Stripe subscription status -> ours. Anything unmapped is left untouched rather
# than guessed at, so a new Stripe status cannot silently cancel a live line.
STRIPE_STATUS = {
    "active": Subscription.Status.ACTIVE,
    "trialing": Subscription.Status.ACTIVE,
    "past_due": Subscription.Status.PAST_DUE,
    "unpaid": Subscription.Status.PAST_DUE,
    "canceled": Subscription.Status.CANCELED,
    "incomplete_expired": Subscription.Status.CANCELED,
    "incomplete": Subscription.Status.INCOMPLETE,
    "paused": Subscription.Status.PAUSED,
}


# ---- pricing ----------------------------------------------------------------
def discount_pct() -> Decimal:
    return Decimal(str(getattr(settings, "SUBSCRIPTION_DISCOUNT_PCT", 15)))


def _charm_down(price: Decimal) -> Decimal:
    """Nearest .49/.99 ending at or BELOW `price`, never below zero.

    apps.catalog.pricing.charm rounds up, which on a cheap plan can land back on
    the one-off price and leave a subscriber paying the same for committing.
    """
    price = max(price, Decimal("0")).quantize(CENT, rounding=ROUND_DOWN)
    whole = int(price)
    frac = price - whole
    if frac >= Decimal("0.99"):
        return Decimal(whole) + Decimal("0.99")
    if frac >= Decimal("0.49"):
        return Decimal(whole) + Decimal("0.49")
    if whole < 1:
        # Under a dollar there is no charm ending at or below the target, and
        # stepping down anyway would price the plan negative. Keep the target.
        return price
    return Decimal(whole - 1) + Decimal("0.99")


def subscription_price(plan) -> Decimal:
    """Per-cycle price.

    A plan on the subscription menu has a price we chose and wrote down; see
    apps.subscriptions.catalogue for why these are chosen rather than computed.
    Anything else falls back to the one-off price less the discount, which is
    what every plan used before the menu existed and what a plan reaching this
    function by another route should still get.

    Original docstring follows.

    Per-cycle price: the one-off price less the subscription discount.

    The discount is the whole reason to subscribe, so it is never merely
    cosmetic — it is the number Stripe charges. Two rails on the rounding: the
    result must stay under the one-off price (otherwise the offer is a lie), and
    it must stay above wholesale plus the minimum margin (otherwise every
    renewal loses money, forever, unattended).
    """
    from apps.subscriptions.catalogue import fixed_price

    agreed = fixed_price(plan)
    if agreed is not None:
        return agreed

    one_off = Decimal(str(plan.price))
    factor = (Decimal("100") - discount_pct()) / Decimal("100")
    target = (one_off * factor).quantize(CENT, rounding=ROUND_HALF_UP)

    price = charm(target)
    if price >= one_off:
        price = _charm_down(target)

    floor = (cost_to_usd(plan.cost_amount, plan.cost_currency)
             + Decimal(str(settings.PRICING_MIN_MARGIN_USD))).quantize(CENT)
    if price < floor:
        price = min(charm(floor), one_off)
    return min(price, one_off).quantize(CENT)


def saving_pct(plan) -> int:
    """Whole-number percentage a subscriber saves against the one-off price."""
    one_off = Decimal(str(plan.price))
    if one_off <= 0:
        return 0
    sub = subscription_price(plan)
    return int(((one_off - sub) / one_off * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def stripe_interval(days: int) -> dict:
    """Map a plan duration onto a Stripe recurring interval.

    7 and 30 days get the natural week/month cadence (calendar months keep the
    renewal date stable). Everything else — 15 days is the common case — bills
    every N days, which Stripe supports up to a year.
    """
    days = int(days or 30)
    if days == 7:
        return {"interval": "week", "interval_count": 1}
    if days == 30:
        return {"interval": "month", "interval_count": 1}
    if days == 365:
        # A year, not three hundred and sixty-five days. Stripe treats them the
        # same for billing and differently for everything a human reads: the
        # customer's card statement, the invoice, and the word the Stripe
        # dashboard shows the operator.
        return {"interval": "year", "interval_count": 1}
    return {"interval": "day", "interval_count": max(1, min(days, 365))}


# ---- Stripe payload helpers -------------------------------------------------
def _dt(ts):
    if not ts:
        return None
    try:
        return datetime.fromtimestamp(int(ts), tz=dt_timezone.utc)
    except (TypeError, ValueError, OSError):
        return None


def _id(value):
    """Stripe fields are either an id string or an expanded object."""
    if isinstance(value, dict):
        return value.get("id") or ""
    return str(value or "")


def _usd(cents):
    if cents in (None, ""):
        return None
    try:
        return (Decimal(str(cents)) / 100).quantize(CENT)
    except (TypeError, ValueError):
        return None


def _subscription_details(invoice: dict) -> list[dict]:
    """Both shapes of an invoice's subscription block, newest first.

    Stripe moved the block under `parent` in the 2025 API versions. Reading both
    means an account-level API upgrade can neither orphan a renewal nor lose the
    metadata we use to find the subscription when the id lookup misses.
    """
    return [d for d in ((invoice.get("parent") or {}).get("subscription_details"),
                        invoice.get("subscription_details")) if isinstance(d, dict)]


def _invoice_subscription_id(invoice: dict) -> str:
    sub = _id(invoice.get("subscription"))
    if sub:
        return sub
    for details in _subscription_details(invoice):
        found = _id(details.get("subscription"))
        if found:
            return found
    return ""


def _invoice_reference(invoice: dict) -> str:
    """Our subscription UUID, mirrored onto the Stripe subscription's metadata."""
    for details in _subscription_details(invoice):
        reference = (details.get("metadata") or {}).get("subscription_id") or ""
        if reference:
            return str(reference)
    return ""


def _invoice_period(invoice: dict):
    for line in ((invoice.get("lines") or {}).get("data") or []):
        period = line.get("period") or {}
        if period.get("start") and period.get("end"):
            return _dt(period["start"]), _dt(period["end"])
    return _dt(invoice.get("period_start")), _dt(invoice.get("period_end"))


def _subscription_period_end(sub_obj: dict):
    end = sub_obj.get("current_period_end")
    if not end:
        # 2025-03-31 and later report the period per subscription item.
        ends = [i.get("current_period_end")
                for i in ((sub_obj.get("items") or {}).get("data") or [])
                if i.get("current_period_end")]
        end = max(ends) if ends else None
    return _dt(end)


def _find_subscription(*, reference="", stripe_subscription_id="") -> Subscription | None:
    if stripe_subscription_id:
        found = Subscription.objects.filter(
            stripe_subscription_id=stripe_subscription_id).first()
        if found:
            return found
    if reference:
        # The reference is our UUID. Anything unparseable makes the UUID lookup
        # raise, so it resolves to "unknown subscription" instead of a 500.
        try:
            return Subscription.objects.filter(pk=str(reference)).first()
        except (ValidationError, ValueError, TypeError):
            return None
    return None


# ---- webhook entry point ----------------------------------------------------
def handle_stripe_event(event) -> None:
    """Single door for every subscription-related Stripe event. Idempotent."""
    etype = str(event.get("type") or "")
    obj = (event.get("data") or {}).get("object") or {}
    if not etype:
        return

    if etype in ("checkout.session.completed", "checkout.session.async_payment_succeeded"):
        if obj.get("mode") == "subscription":
            _on_checkout_completed(obj)
    elif etype in ("invoice.paid", "invoice.payment_succeeded"):
        _on_invoice_paid(obj)
    elif etype == "invoice.payment_failed":
        _on_invoice_failed(obj)
    elif etype in ("customer.subscription.created", "customer.subscription.updated",
                   "customer.subscription.deleted", "customer.subscription.paused",
                   "customer.subscription.resumed"):
        _on_subscription_changed(obj, deleted=etype.endswith(".deleted"))


def _on_checkout_completed(session: dict) -> None:
    reference = session.get("client_reference_id") or \
        (session.get("metadata") or {}).get("subscription_id") or ""
    stripe_sub_id = _id(session.get("subscription"))
    sub = _find_subscription(reference=reference, stripe_subscription_id=stripe_sub_id)
    if sub is None:
        log.warning("Subscription checkout for unknown reference %r", reference)
        return

    sub.stripe_customer_id = _id(session.get("customer")) or sub.stripe_customer_id
    sub.stripe_subscription_id = stripe_sub_id or sub.stripe_subscription_id
    sub.last_error = ""
    if str(session.get("payment_status") or "") in ("paid", "no_payment_required"):
        sub.status = Subscription.Status.ACTIVE
        sub.started_at = sub.started_at or timezone.now()

    invoice_id = _id(session.get("invoice"))
    period_start = period_end = None

    if sub.stripe_subscription_id:
        try:
            remote = retrieve_subscription(sub.stripe_subscription_id)
        except SubscriptionError as e:
            log.warning("Could not read Stripe subscription %s: %s",
                        sub.stripe_subscription_id, e)
        else:
            _apply_remote(sub, remote)
            invoice_id = invoice_id or _id(remote.get("latest_invoice"))
            period_start = _dt(remote.get("current_period_start")) or \
                _first_item_period_start(remote)
            period_end = sub.current_period_end

    if sub.current_period_end is None:
        sub.current_period_end = timezone.now() + timedelta(days=sub.interval_days)
    sub.save()

    if sub.status != Subscription.Status.ACTIVE:
        # The session completed but the money has not actually cleared — a
        # pending SCA challenge, or a decline at the last step. Provisioning now
        # would hand out data we were never paid for; invoice.paid starts the
        # cycle if and when the charge succeeds.
        log.info("Subscription %s completed checkout but is %s", sub.pk, sub.status)
        return

    if not invoice_id:
        # No invoice id means no safe dedupe key: leave the first cycle to the
        # invoice.paid webhook rather than risk provisioning the period twice.
        log.warning("Subscription %s checkout carried no invoice id", sub.pk)
        return

    amount = _usd(session.get("amount_total")) or sub.price_usd
    start_cycle(sub, stripe_invoice_id=invoice_id,
                period_start=period_start or timezone.now(),
                period_end=period_end or sub.current_period_end,
                amount_usd=amount)


def _first_item_period_start(remote: dict):
    starts = [i.get("current_period_start")
              for i in ((remote.get("items") or {}).get("data") or [])
              if i.get("current_period_start")]
    return _dt(min(starts)) if starts else None


def _on_invoice_paid(invoice: dict) -> None:
    stripe_sub_id = _invoice_subscription_id(invoice)
    if not stripe_sub_id:
        return  # a one-off invoice; apps.payments owns those
    sub = _find_subscription(stripe_subscription_id=stripe_sub_id,
                            reference=_invoice_reference(invoice))
    if sub is None:
        log.warning("invoice.paid for unknown subscription %s", stripe_sub_id)
        return

    invoice_id = _id(invoice.get("id"))
    if not invoice_id:
        return
    period_start, period_end = _invoice_period(invoice)
    amount = _usd(invoice.get("amount_paid"))
    if amount is None:
        amount = _usd(invoice.get("total")) or sub.price_usd

    if period_end:
        sub.current_period_end = period_end
    sub.status = Subscription.Status.ACTIVE
    sub.started_at = sub.started_at or timezone.now()
    sub.stripe_customer_id = sub.stripe_customer_id or _id(invoice.get("customer"))
    sub.last_error = ""
    sub.save(update_fields=["current_period_end", "status", "started_at",
                            "stripe_customer_id", "last_error", "updated_at"])

    start_cycle(sub, stripe_invoice_id=invoice_id,
                period_start=period_start or timezone.now(),
                period_end=period_end or sub.current_period_end,
                amount_usd=amount)


def _on_invoice_failed(invoice: dict) -> None:
    stripe_sub_id = _invoice_subscription_id(invoice)
    sub = _find_subscription(stripe_subscription_id=stripe_sub_id,
                             reference=_invoice_reference(invoice))
    if sub is None:
        return
    sub.status = Subscription.Status.PAST_DUE
    sub.last_error = "Stripe reported a failed payment for the latest invoice."
    sub.save(update_fields=["status", "last_error", "updated_at"])

    invoice_id = _id(invoice.get("id"))
    # Stripe dunning retries the same invoice several times over two weeks and
    # fires this event on every attempt. Only the first attempt is news: the
    # customer is told once what to do, and the operator gets one alert.
    first_failure = True
    if invoice_id:
        period_start, period_end = _invoice_period(invoice)
        # Recorded so the customer's billing history shows the failed attempt.
        # Never downgrade a cycle that is already paid: webhooks can arrive out
        # of order, and a paid period must stay paid.
        cycle, created = SubscriptionCycle.objects.get_or_create(
            stripe_invoice_id=invoice_id,
            defaults={
                "subscription": sub,
                "period_start": period_start,
                "period_end": period_end,
                "amount_usd": _usd(invoice.get("amount_due")) or sub.price_usd,
                "status": SubscriptionCycle.Status.FAILED,
                "error": "Card declined.",
            },
        )
        first_failure = created
        if not created and cycle.status != SubscriptionCycle.Status.PAID:
            cycle.status = SubscriptionCycle.Status.FAILED
            cycle.error = "Card declined."
            cycle.save(update_fields=["status", "error"])

    if not first_failure:
        log.info("Stripe retried failed invoice %s for subscription %s; no re-notify",
                 invoice_id, sub.pk)
        return

    send_payment_failed(sub)
    notify_admin(
        f"Subscription payment failed — {sub.user.email}",
        [f"Plan: {sub.title}", f"Amount: ${sub.price_usd}",
         f"Stripe subscription: {sub.stripe_subscription_id or '-'}",
         "The customer has been emailed. Stripe will retry automatically."],
    )


def _on_subscription_changed(obj: dict, *, deleted: bool = False) -> None:
    sub = _find_subscription(
        stripe_subscription_id=_id(obj.get("id")),
        reference=((obj.get("metadata") or {})).get("subscription_id", ""),
    )
    if sub is None:
        return
    _apply_remote(sub, obj, force_canceled=deleted)
    sub.save()


def _apply_remote(sub: Subscription, remote: dict, *, force_canceled: bool = False) -> None:
    """Copy Stripe's view of the subscription onto our row (no save)."""
    was_canceled = sub.status == Subscription.Status.CANCELED
    status = STRIPE_STATUS.get(str(remote.get("status") or ""))
    if force_canceled:
        status = Subscription.Status.CANCELED
    if status:
        sub.status = status
    sub.cancel_at_period_end = bool(remote.get("cancel_at_period_end"))
    period_end = _subscription_period_end(remote)
    if period_end:
        sub.current_period_end = period_end
    customer = _id(remote.get("customer"))
    if customer:
        sub.stripe_customer_id = customer
    if not sub.stripe_subscription_id:
        sub.stripe_subscription_id = _id(remote.get("id")) or None
    if sub.status == Subscription.Status.CANCELED:
        if sub.canceled_at is None:
            sub.canceled_at = _dt(remote.get("canceled_at")) or timezone.now()
    elif was_canceled and sub.status == Subscription.Status.ACTIVE:
        # A genuine reactivation in Stripe: the old cancellation no longer
        # describes this line. Every other case keeps the timestamp, so a
        # routine sync cannot quietly erase when the customer cancelled.
        sub.canceled_at = None


def sync_subscription(sub: Subscription) -> Subscription:
    """Pull the authoritative state from Stripe (admin action, support tooling)."""
    if not sub.stripe_subscription_id:
        raise SubscriptionError("This subscription never reached Stripe.")
    _apply_remote(sub, retrieve_subscription(sub.stripe_subscription_id))
    sub.save()
    return sub


# ---- cycles -----------------------------------------------------------------
def resolve_esim(subscription: Subscription):
    """The eSIM this subscription keeps alive, recovered from order history.

    `_provision_cycle` binds the line, but it is not the only path that can
    provision one: a first cycle that fails at the provider is finished later by
    apps.orders.services.retry_failed or the orders admin retry, and neither
    knows about subscriptions. Reading the line back off the cycles' orders is
    what stops the next renewal from being mistaken for a first cycle and
    issuing the customer a second profile.
    """
    if subscription.esim_id:
        return subscription.esim
    order_ids = list(SubscriptionCycle.objects.filter(subscription=subscription)
                     .exclude(order=None).values_list("order_id", flat=True))
    if not order_ids:
        return None
    esim = (Esim.objects.filter(order_id__in=order_ids).order_by("created_at").first()
            or Esim.objects.filter(topups__id__in=order_ids).order_by("created_at").first())
    if esim is not None:
        _bind_esim(subscription, esim, order_ids=order_ids)
    return esim


def _bind_esim(subscription: Subscription, esim, *, order_ids=None) -> None:
    """Attach the line to the subscription and to any renewal still waiting for it."""
    Subscription.objects.filter(pk=subscription.pk).update(esim=esim)
    subscription.esim = esim
    if order_ids:
        # A renewal billed while the first cycle was still stuck was written
        # with no top-up target. Point it at the line now, so the orders retry
        # sweeper can finish it instead of failing for ever.
        Order.objects.filter(id__in=order_ids, kind=Order.Kind.TOPUP,
                             target_esim__isnull=True,
                             status=Order.Status.PAID).update(target_esim=esim)


def _record_payment(order: Order, subscription: Subscription, *,
                    stripe_invoice_id: str, amount: Decimal) -> None:
    """Mirror a cycle's charge into the payments ledger.

    Stripe Billing collects subscription money on its own, so apps.payments
    never sees the charge and would otherwise report zero revenue for every
    subscriber. Keyed on the Stripe invoice id, which is also what reconciliation
    against a Stripe payout report matches on.
    """
    Payment.objects.get_or_create(
        provider=Payment.Provider.STRIPE,
        provider_payment_id=stripe_invoice_id,
        defaults={
            "order": order,
            "user": subscription.user,
            "amount_usd": amount,
            "paid_amount_usd": amount,
            "status": Payment.Status.PAID,
            "settled": True,
            "raw": {"source": "subscription_cycle",
                    "subscription_id": str(subscription.pk),
                    "stripe_invoice_id": stripe_invoice_id},
        },
    )


@transaction.atomic
def start_cycle(subscription: Subscription, *, stripe_invoice_id: str,
                period_start, period_end, amount_usd,
                from_balance: bool = False) -> SubscriptionCycle:
    """Record a paid period and provision it. Safe to call twice.

    get_or_create on the reference is the whole defence: Stripe retries
    webhooks, and the first cycle arrives on both checkout.session.completed and
    invoice.paid. A call for an already-provisioned invoice returns that cycle
    untouched; one for an invoice previously recorded as failed revives it, so a
    successful Stripe retry provisions exactly once.

    `stripe_invoice_id` is the column's name and a card cycle's Stripe invoice.
    A balance cycle has no invoice, so it carries a locally minted `bal_...`
    reference instead -- the same uniqueness, the same idempotency, no second
    column to keep in step.

    `from_balance` decides how the cycle is settled, and the difference is not
    cosmetic. A card cycle's money arrives from outside and is mirrored into the
    payments ledger. A balance cycle spends credit that was already recorded as
    revenue when it was bought, so it is a wallet debit: writing a Payment for
    it as well would count the same dollar twice. Debiting inside this atomic
    block is also what makes a short balance safe -- InsufficientBalance rolls
    the order and the cycle back rather than provisioning something unpaid.
    """
    sub = Subscription.objects.select_for_update().select_related("plan", "user").get(
        pk=subscription.pk)
    amount = Decimal(str(amount_usd or sub.price_usd)).quantize(CENT)

    cycle, created = SubscriptionCycle.objects.get_or_create(
        stripe_invoice_id=stripe_invoice_id,
        defaults={
            "subscription": sub,
            "period_start": period_start,
            "period_end": period_end,
            "amount_usd": amount,
            "status": SubscriptionCycle.Status.PAID,
        },
    )
    if not created:
        if cycle.status == SubscriptionCycle.Status.PAID and cycle.order_id:
            return cycle
        # This invoice was recorded as a failed attempt and Stripe has since
        # collected it. Revive the same row rather than minting a second one, so
        # the retry provisions exactly once.
        cycle.status = SubscriptionCycle.Status.PAID
        cycle.amount_usd = amount
        cycle.period_start = period_start or cycle.period_start
        cycle.period_end = period_end or cycle.period_end
        cycle.error = ""
        cycle.save(update_fields=["status", "amount_usd", "period_start",
                                  "period_end", "error"])

    plan = sub.plan
    esim = resolve_esim(sub)
    # A cycle issues a new eSIM only when no period has ever been billed. The
    # bound eSIM is not the test: the first cycle's provisioning can fail and be
    # retried out of band, and a renewal that read `esim is None` would order a
    # second profile while the first one was still on its way.
    first_cycle = esim is None and not (
        SubscriptionCycle.objects
        .filter(subscription=sub, status=SubscriptionCycle.Status.PAID,
                order__isnull=False)
        .exclude(pk=cycle.pk).exists())

    # A top-up needs a line to top up. If an earlier cycle was billed but its
    # provisioning is still stuck, there is no eSIM to attach to, and an order of
    # kind TOPUP with target_esim NULL can never be fulfilled by anything -- not
    # the sweeper, not the admin action. The customer has paid, so issue a fresh
    # profile instead of booking work that cannot be done.
    if not first_cycle and esim is None:
        log.warning(
            "subscription %s has no bound eSIM at renewal; issuing a new profile "
            "rather than a top-up with no target", sub.pk,
        )
        first_cycle = True
    order = Order.objects.create(
        user=sub.user,
        email=sub.user.email,
        kind=Order.Kind.NEW if first_cycle else Order.Kind.TOPUP,
        plan=plan,
        plan_title=plan.title,
        plan_provider_id=plan.provider_plan_id,
        plan_days=plan.days,
        plan_data_label=plan.data_label,
        # The subscription discount is priced into the recurring charge itself,
        # so the cycle has no coupon line: subtotal is what we billed.
        subtotal_usd=amount,
        amount_usd=amount,
        cost_amount=plan.cost_amount,
        cost_currency=plan.cost_currency,
        target_esim=esim,
    )
    if from_balance:
        # Raises InsufficientBalance, which unwinds everything above it.
        Wallet.debit(sub.user, amount, order=order,
                     description=f"{plan.title} — subscription")
    order.mark_paid()
    if not from_balance:
        _record_payment(order, sub, stripe_invoice_id=stripe_invoice_id, amount=amount)

    cycle.order = order
    cycle.save(update_fields=["order"])

    if not first_cycle:
        sub.renewals_count += 1
    sub.save(update_fields=["renewals_count", "updated_at"])

    transaction.on_commit(lambda: _provision_cycle(cycle.pk, order.pk, sub.pk, first_cycle))
    return cycle


def _provision_cycle(cycle_id, order_id, subscription_id, first_cycle: bool) -> None:
    """Run fulfilment for a cycle we have already recorded as paid.

    Failure here must never lose the cycle: the money is taken, the row stands,
    the operator is emailed and the existing retry_failed sweeper picks the order
    up like any other stuck order.
    """
    from apps.orders.services import fulfill_order

    sub = Subscription.objects.select_related("plan", "user").filter(pk=subscription_id).first()
    try:
        order = fulfill_order(order_id)
    except Exception as e:  # noqa: BLE001
        log.exception("subscription cycle fulfilment failed (cycle %s)", cycle_id)
        SubscriptionCycle.objects.filter(pk=cycle_id).update(error=str(e)[:2000])
        if sub is not None:
            Subscription.objects.filter(pk=sub.pk).update(last_error=str(e)[:2000])
            notify_admin(
                f"Subscription cycle NOT provisioned — {sub.user.email}",
                [f"Plan: {sub.title}", f"Cycle: {cycle_id}", f"Order: {order_id}",
                 f"Error: {e}", "The cycle is paid and recorded. Retry from the orders admin."],
            )
        return

    esim = order.esims.first() or order.target_esim
    if sub is None or esim is None:
        return
    if sub.esim_id is None:
        # Bind the line on the first cycle so every renewal tops up this same
        # eSIM — the customer installs one profile, once, and never again.
        _bind_esim(sub, esim, order_ids=list(
            SubscriptionCycle.objects.filter(subscription=sub)
            .exclude(order=None).values_list("order_id", flat=True)))

    if first_cycle:
        send_started(sub, esim)
    else:
        send_renewed(sub, esim)


# ---- emails -----------------------------------------------------------------
def _email_ctx(sub: Subscription, esim=None) -> dict:
    return {
        "subscription": sub,
        "esim": esim,
        "plan": sub.plan,
        "detail_url": f"{settings.SITE_URL}{sub.get_absolute_url()}",
    }


def send_started(sub: Subscription, esim=None) -> None:
    send_email_bg(
        sub.user.email,
        f"Your {sub.target_name} subscription is live",
        "subscription_started", _email_ctx(sub, esim),
    )


def send_renewed(sub: Subscription, esim=None) -> None:
    send_email_bg(
        sub.user.email,
        f"Your {sub.target_name} data has been renewed",
        "subscription_renewed", _email_ctx(sub, esim),
    )


def send_payment_failed(sub: Subscription) -> None:
    send_email_bg(
        sub.user.email,
        f"We could not renew your {sub.target_name} subscription",
        "subscription_payment_failed", _email_ctx(sub, sub.esim),
    )


# ---- subscriptions paid out of balance --------------------------------------
#
# The app's half of the feature. It has no card -- balance is the only thing it
# spends -- so a subscription it could only start in a browser was a
# subscription it could not sell. Here the wallet is the mandate: the customer
# holds credit, we debit it on our own schedule, and there is nothing for a
# store to have an opinion about because no payment is taken.
#
# What Stripe Billing does for a card subscription, renew_subscriptions does for
# this one. The difference that matters is what happens when the money is not
# there: a card gets retried by Stripe's dunning for a fortnight, a balance
# simply is not enough, so the line goes past_due immediately, the customer is
# told what it costs to fix, and the grace window below decides how long we keep
# the line reserved before giving up.

# How long a subscription stays past_due before it is cancelled. Long enough to
# notice an email and top up over a weekend; short enough that a line nobody is
# paying for is not held open for ever.
PAST_DUE_GRACE = timedelta(days=5)


def _balance_reference() -> str:
    """The unique reference a balance cycle is keyed on.

    Random rather than sequential: the cycle before this one already exists, and
    a counter would need a lock to stay unique under two renewals at once.
    """
    return f"bal_{uuid.uuid4().hex}"


class SubscriptionNotAvailable(Exception):
    """This plan cannot be subscribed to, or not by this customer right now."""


def live_subscription(user, plan) -> Subscription | None:
    """This customer's running subscription for this plan, if any.

    Never let one customer run two for the same plan: that is two charges and
    two eSIMs for one line they thought they were renewing.
    """
    return (Subscription.objects
            .filter(user=user, plan=plan,
                    status__in=[Subscription.Status.ACTIVE,
                                Subscription.Status.PAST_DUE,
                                Subscription.Status.PAUSED])
            .first())


@transaction.atomic
def start_with_balance(user, plan) -> Subscription:
    """Begin a subscription and pay its first period out of balance.

    Raises SubscriptionNotAvailable for a plan that is not on the menu, or a
    customer who already has this one running, and InsufficientBalance when the
    credit is short -- in which case nothing at all is created.
    """
    from .catalogue import is_subscribable

    if not is_subscribable(plan):
        raise SubscriptionNotAvailable("That plan is not sold as a subscription.")
    if live_subscription(user, plan) is not None:
        raise SubscriptionNotAvailable("You already have a subscription for this plan.")

    price = subscription_price(plan)
    now = timezone.now()
    period_end = now + timedelta(days=plan.days or 30)

    sub = Subscription.objects.create(
        user=user, plan=plan, price_usd=price, interval_days=plan.days or 30,
        funding=Subscription.Funding.BALANCE,
        status=Subscription.Status.ACTIVE,
        started_at=now, current_period_end=period_end,
    )
    # Raises InsufficientBalance, which rolls the subscription back with it.
    start_cycle(sub, stripe_invoice_id=_balance_reference(), period_start=now,
                period_end=period_end, amount_usd=price, from_balance=True)
    transaction.on_commit(lambda: send_started(sub))
    return sub


def due_for_renewal(now=None):
    """Balance subscriptions whose period has run out.

    past_due is included on purpose: that is a renewal that has already been
    tried and found the balance short, and the customer topping up should be
    picked up by the next run rather than needing anybody to do anything.
    """
    now = now or timezone.now()
    return (Subscription.objects
            .filter(funding=Subscription.Funding.BALANCE,
                    status__in=[Subscription.Status.ACTIVE, Subscription.Status.PAST_DUE],
                    current_period_end__lte=now)
            .select_related("user", "plan", "plan__country", "plan__region")
            .order_by("current_period_end"))


def renew_with_balance(sub: Subscription) -> SubscriptionCycle | None:
    """Charge one more period to the wallet, or mark the line past due.

    Returns the cycle, or None when the balance was short. Never raises for a
    short balance: this runs in a loop over every due subscription, and one
    customer who has not topped up must not stop the rest from renewing.
    """
    if sub.cancel_at_period_end:
        cancel_now(sub, reason="cancelled at period end")
        return None

    period_start = sub.current_period_end or timezone.now()
    period_end = period_start + timedelta(days=sub.interval_days or 30)
    try:
        cycle = start_cycle(sub, stripe_invoice_id=_balance_reference(),
                            period_start=period_start, period_end=period_end,
                            amount_usd=sub.price_usd, from_balance=True)
    except InsufficientBalance as e:
        _mark_past_due(sub, str(e))
        return None

    Subscription.objects.filter(pk=sub.pk).update(
        status=Subscription.Status.ACTIVE, current_period_end=period_end,
        last_error="", updated_at=timezone.now(),
    )
    sub.refresh_from_db(fields=["status", "current_period_end", "last_error"])
    transaction.on_commit(lambda: send_renewed(sub, sub.esim))
    return cycle


def _mark_past_due(sub: Subscription, reason: str) -> None:
    """The balance was short. Tell them once, then give up after the grace.

    Once, because this runs on a schedule and a daily "your subscription failed"
    email is how a customer learns to filter you. The first failure is the one
    that carries information; the rest are the same sentence.
    """
    first_failure = sub.status != Subscription.Status.PAST_DUE
    overdue = timezone.now() - (sub.current_period_end or timezone.now())

    if not first_failure and overdue > PAST_DUE_GRACE:
        cancel_now(sub, reason=f"balance short for more than {PAST_DUE_GRACE.days} days")
        return

    Subscription.objects.filter(pk=sub.pk).update(
        status=Subscription.Status.PAST_DUE, last_error=reason[:500],
        updated_at=timezone.now())
    sub.status = Subscription.Status.PAST_DUE
    sub.last_error = reason
    if first_failure:
        transaction.on_commit(lambda: send_payment_failed(sub))


def cancel_now(sub: Subscription, *, reason: str = "") -> Subscription:
    """Stop the subscription immediately. The eSIM keeps whatever it has left.

    Nothing is refunded and nothing is taken away: the period they paid for is
    on the line already. Cancelling stops the next debit, which is what the
    customer means by it.
    """
    Subscription.objects.filter(pk=sub.pk).update(
        status=Subscription.Status.CANCELED, canceled_at=timezone.now(),
        cancel_at_period_end=False, last_error=reason[:500], updated_at=timezone.now())
    sub.status = Subscription.Status.CANCELED
    sub.canceled_at = timezone.now()
    return sub


def cancel_at_period_end(sub: Subscription) -> Subscription:
    """Stop renewing, but leave the period they have paid for running.

    The kinder default and the one a customer expects from "cancel": they paid
    for a month, they keep the month. A line already past due has no paid period
    left to run out, so that one stops now.
    """
    if sub.status == Subscription.Status.PAST_DUE:
        return cancel_now(sub, reason="cancelled while past due")
    Subscription.objects.filter(pk=sub.pk).update(
        cancel_at_period_end=True, updated_at=timezone.now())
    sub.cancel_at_period_end = True
    return sub


def resume(sub: Subscription) -> Subscription:
    """Undo a cancel_at_period_end, while the period is still running."""
    if sub.status == Subscription.Status.CANCELED:
        raise SubscriptionNotAvailable("That subscription has already ended.")
    Subscription.objects.filter(pk=sub.pk).update(
        cancel_at_period_end=False, updated_at=timezone.now())
    sub.cancel_at_period_end = False
    return sub
