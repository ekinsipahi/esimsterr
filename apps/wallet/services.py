"""Balance top-up presets, bonuses, and paying for an order out of credit."""
from __future__ import annotations

import logging
from decimal import ROUND_HALF_UP, Decimal

from django.conf import settings
from django.db import transaction
from django.utils.translation import gettext_lazy as _

from .models import BalanceTopUp, InsufficientBalance, Wallet, WalletTransaction

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

        Wallet.credit(topup.user, topup.amount_usd,
                      kind=WalletTransaction.Kind.TOPUP,
                      description=f"Top-up {topup.ref}", balance_topup=topup)
        if topup.bonus_usd > 0:
            Wallet.credit(topup.user, topup.bonus_usd,
                          kind=WalletTransaction.Kind.BONUS,
                          description=f"Bonus on {topup.ref}", balance_topup=topup)
        topup.mark_credited()

    log.info("Credited %s: $%s + $%s bonus to %s",
             topup.ref, topup.amount_usd, topup.bonus_usd, topup.user.email)
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
    from apps.orders.services import fulfill_order

    with transaction.atomic():
        tx = Wallet.debit(user, order.amount_usd,
                          description=f"{order.plan_title} ({order.ref})", order=order)
        order.mark_paid()

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
