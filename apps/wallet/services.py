"""Balance top-up presets, bonuses, and paying for an order out of credit."""
from __future__ import annotations

import logging
from decimal import ROUND_HALF_UP, Decimal

from django.conf import settings
from django.db import models, transaction
from django.utils.translation import gettext_lazy as _

from .models import (AlreadyPaid, BalanceTopUp, InsufficientBalance, ReferralPayout,
                     Wallet, WalletTransaction)

log = logging.getLogger(__name__)
CENT = Decimal("0.01")


def _money(v) -> Decimal:
    return Decimal(str(v or 0)).quantize(CENT, rounding=ROUND_HALF_UP)


def bonus_tiers() -> list[tuple[Decimal, Decimal]]:
    """[(pay, bonus)] descending, parsed from WALLET_BONUS_TIERS.

    A setting rather than a table: the tiers are a marketing lever that changes
    with a campaign, and a deploy is a cheaper way to change them than an admin
    screen nobody audits.
    """
    raw = getattr(settings, "WALLET_BONUS_TIERS", "") or ""
    tiers = []
    for chunk in raw.split(","):
        chunk = chunk.strip()
        if not chunk or ":" not in chunk:
            continue
        pay, bonus = chunk.split(":", 1)
        try:
            tiers.append((_money(pay), _money(bonus)))
        except Exception:  # noqa: BLE001
            continue
    return sorted(tiers, key=lambda t: t[0], reverse=True)


def bonus_for(amount) -> Decimal:
    """The bonus earned by paying `amount`. Highest tier reached wins."""
    amount = _money(amount)
    for pay, bonus in bonus_tiers():
        if amount >= pay:
            return bonus
    return Decimal("0.00")


def presets() -> list[dict]:
    """The amounts offered as buttons, cheapest first, with their bonus."""
    out = []
    for pay, bonus in sorted(bonus_tiers(), key=lambda t: t[0]):
        total = _money(pay + bonus)
        pct = int((bonus / pay * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP)) if pay else 0
        out.append({"amount": pay, "bonus": bonus, "total": total, "bonus_pct": pct})
    return out


def limits() -> tuple[Decimal, Decimal]:
    return (_money(getattr(settings, "WALLET_MIN_TOPUP_USD", "5.00")),
            _money(getattr(settings, "WALLET_MAX_TOPUP_USD", "500.00")))


def validate_amount(amount) -> Decimal:
    """Normalise a requested top-up, or raise ValueError with a sayable reason."""
    try:
        amount = _money(amount)
    except Exception as e:  # noqa: BLE001
        raise ValueError(_("Enter an amount.")) from e
    low, high = limits()
    if amount < low:
        raise ValueError(_("The smallest top-up is $%(low)s.") % {"low": low})
    if amount > high:
        raise ValueError(_("The largest single top-up is $%(high)s.") % {"high": high})
    return amount


def create_topup(user, amount, *, source: str = "web", ip=None) -> BalanceTopUp:
    amount = validate_amount(amount)
    return BalanceTopUp.objects.create(
        user=user, amount_usd=amount, bonus_usd=bonus_for(amount),
        source=(source or "web")[:12], ip=ip,
    )


def credit_topup(topup: BalanceTopUp) -> BalanceTopUp:
    """Move a paid top-up into the wallet. Idempotent.

    The guard is the status, checked inside the row lock: a Stripe webhook and
    the return-page settlement routinely both arrive, and crediting twice is
    giving money away.
    """
    with transaction.atomic():
        topup = BalanceTopUp.objects.select_for_update().get(pk=topup.pk)
        if topup.status == BalanceTopUp.Status.CREDITED:
            return topup

        # Read what the provider says actually arrived rather than trusting the
        # invoice. Stripe sends the exact captured amount; a crypto invoice
        # frequently settles over the quote because the rate moved between
        # quoting and confirmation, and that difference belongs to the customer.
        payment = topup.payments.order_by("-created_at").first()
        if payment is not None and payment.paid_amount_usd is not None:
            topup.received_usd = _money(payment.paid_amount_usd)
            topup.save(update_fields=["received_usd"])

        payable = topup.payable_usd()
        Wallet.credit(topup.user, payable,
                      kind=WalletTransaction.Kind.TOPUP,
                      description=f"Top-up {topup.ref}", balance_topup=topup)
        if topup.bonus_usd > 0:
            Wallet.credit(topup.user, topup.bonus_usd,
                          kind=WalletTransaction.Kind.BONUS,
                          description=f"Bonus on {topup.ref}", balance_topup=topup)
        topup.mark_credited(payable + _money(topup.bonus_usd))

    over = topup.payable_usd() - _money(topup.amount_usd)
    reported = (f"${topup.received_usd}" if topup.received_usd is not None
                else "no amount reported")
    log.info(
        "Credited %s to %s: invoiced $%s, provider said %s, credited $%s (+ $%s bonus)%s",
        topup.ref, topup.user.email, topup.amount_usd, reported,
        topup.payable_usd(), topup.bonus_usd,
        f" — OVERPAID by ${over}, credited in full" if over > 0 else "",
    )
    pay_referral_if_due(topup.user)
    from .notifications import topup_alert
    topup_alert(topup)
    from apps.accounts.emails import send_balance_added
    send_balance_added(topup)
    return topup


def can_pay_with_balance(user, amount) -> bool:
    if not getattr(user, "is_authenticated", False):
        return False
    wallet = Wallet.objects.filter(user=user).first()
    return bool(wallet and wallet.balance_usd >= _money(amount))


def pay_order_with_balance(user, order) -> WalletTransaction:
    """Spend credit on an order and release it for provisioning.

    Raises InsufficientBalance rather than partially charging. The debit and the
    order's PAID transition happen in one database transaction so a crash
    between them cannot take the money without delivering the plan.
    """
    from apps.orders.models import Order
    from apps.orders.services import fulfill_order

    with transaction.atomic():
        # Re-read under a lock and check it is still unpaid. Both callers build
        # a fresh order and pay it once, so today this changes nothing -- which
        # is exactly when it is worth writing, because the next caller to reach
        # for this function will be paying an order that already exists, and
        # paying one twice takes the money twice.
        locked = Order.objects.select_for_update().get(pk=order.pk)
        if locked.user_id != getattr(user, "pk", None):
            raise InsufficientBalance("That order belongs to a different account.")
        if locked.status != Order.Status.PENDING:
            raise AlreadyPaid(f"Order {locked.ref} is already {locked.status}.")
        tx = Wallet.debit(user, locked.amount_usd,
                          description=f"{locked.plan_title} ({locked.ref})", order=locked)
        locked.mark_paid()
        order.status = locked.status

    def _provision():
        try:
            fulfill_order(order.pk)
        except Exception:  # noqa: BLE001
            log.exception("balance-paid fulfilment failed for %s", order.ref)

    transaction.on_commit(_provision)
    return tx


def refund_to_balance(order, amount=None, *, reason: str = "") -> WalletTransaction | None:
    """Put money back as credit. Used where a card refund is not possible or the
    customer prefers credit -- never silently instead of a refund they asked for."""
    if order.user_id is None:
        return None
    amount = _money(amount if amount is not None else order.amount_usd)
    if amount <= 0:
        return None
    return Wallet.credit(order.user, amount, kind=WalletTransaction.Kind.REFUND,
                         description=(reason or f"Refund for {order.ref}")[:200], order=order)


def referral_settings() -> tuple[Decimal, Decimal]:
    return (_money(getattr(settings, "REFERRAL_BONUS_USD", "3.00")),
            _money(getattr(settings, "REFERRAL_MIN_TOPUP_USD", "5.00")))


def referral_progress(user) -> dict:
    """What this customer's invitations have earned, and what is still pending.

    Counting "signed up" separately from "paid out" matters: an invite that has
    not topped up yet is not a failure, it is a reminder worth sending.
    """
    bonus, threshold = referral_settings()
    invited = user.referrals.count()
    paid = user.referral_payouts.count()
    earned = sum((p.amount_usd for p in user.referral_payouts.all()), Decimal("0.00"))
    return {
        "code": user.referral_code or "",
        "invited": invited,
        "rewarded": paid,
        "pending": max(0, invited - paid),
        "earned_usd": _money(earned),
        "bonus_usd": bonus,
        "min_topup_usd": threshold,
    }


def pay_referral_if_due(user) -> ReferralPayout | None:
    """Reward the person who invited `user`, once they have topped up enough.

    Deliberately triggered by a top-up rather than by signing up. A reward for
    registering pays for empty accounts; a reward for money arriving pays for
    customers. The threshold is the referred customer's own paid top-ups --
    bonus credit excluded, or the bonus would help clear the bar it granted.
    """
    referrer = getattr(user, "referred_by", None)
    if referrer is None or referrer.pk == user.pk:
        return None
    if ReferralPayout.objects.filter(referred=user).exists():
        return None

    bonus, threshold = referral_settings()
    paid_in = BalanceTopUp.objects.filter(
        user=user, status=BalanceTopUp.Status.CREDITED,
    ).aggregate(total=models.Sum("amount_usd"))["total"] or Decimal("0.00")
    paid_in = _money(paid_in)
    if paid_in < threshold:
        return None

    with transaction.atomic():
        # get_or_create under the unique constraint: two top-ups settling at
        # once would otherwise both pass the check above and both pay.
        payout, created = ReferralPayout.objects.get_or_create(
            referred=user,
            defaults={"referrer": referrer, "amount_usd": bonus,
                      "qualifying_topup_usd": paid_in},
        )
        if not created:
            return payout
        Wallet.credit(referrer, bonus, kind=WalletTransaction.Kind.BONUS,
                      description=f"Referral reward — {user.email}")

    log.info("Referral payout $%s to %s for %s", bonus, referrer.email, user.email)
    try:
        from apps.accounts.emails import send_referral_reward
        send_referral_reward(referrer, user, bonus)
    except Exception:  # noqa: BLE001
        log.exception("referral reward email failed")
    return payout
