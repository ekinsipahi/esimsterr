"""Store credit: a balance the customer tops up once and spends many times.

Two reasons this exists rather than charging a card each time. It is the
difference between a three-tap purchase and a browser round trip, and -- the
reason it matters on mobile -- spending credit you already own is not a payment
transaction, so it does not touch the app stores' payment rules at all. Topping
the balance up happens on the website, in the system browser, exactly like
buying a plan does.

The balance is a **ledger**, not a number. `Wallet.balance_usd` is a cached
total; `WalletTransaction` is the truth, every row carrying the balance that
resulted from it. Money that exists only as a mutable integer is money you
cannot audit after the first dispute.

Naming, deliberately: in this codebase "top-up" already means adding data to a
live eSIM. Store credit is "balance" everywhere -- models, URLs, UI copy -- so
the two can never be confused in a support ticket or a refund.
"""
from __future__ import annotations

import uuid
from decimal import ROUND_HALF_UP, Decimal

from django.conf import settings
from django.db import models, transaction
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

CENT = Decimal("0.01")


def _money(value) -> Decimal:
    return Decimal(str(value or 0)).quantize(CENT, rounding=ROUND_HALF_UP)


class InsufficientBalance(Exception):
    """Raised instead of allowing a wallet to go negative."""


class Wallet(models.Model):
    """One per customer. Created on demand, never deleted while orders exist."""

    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
                                related_name="wallet", verbose_name=_("customer"))
    balance_usd = models.DecimalField(_("balance"), max_digits=10, decimal_places=2,
                                      default=Decimal("0.00"))
    # Lifetime figures, kept denormalised so the account page does not aggregate
    # the whole ledger on every render.
    topped_up_usd = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    spent_usd = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _("wallet")
        verbose_name_plural = _("wallets")

    def __str__(self):
        return f"{self.user.email}: ${self.balance_usd}"

    @classmethod
    def for_user(cls, user) -> "Wallet":
        wallet, _created = cls.objects.get_or_create(user=user)
        return wallet

    # -- movements ----------------------------------------------------------
    @classmethod
    def _apply(cls, user, kind: str, amount: Decimal, *, description: str = "",
               order=None, balance_topup=None) -> "WalletTransaction":
        """Move money and write the ledger row in one transaction.

        select_for_update is the whole point: two tabs pressing "pay with
        balance" at the same moment would otherwise both read the old balance and
        both succeed, and the wallet would fund one plan twice.
        """
        amount = _money(amount)
        if amount <= 0:
            raise ValueError("A wallet movement must be a positive amount.")

        with transaction.atomic():
            wallet = (cls.objects.select_for_update()
                      .get_or_create(user=user)[0] if not isinstance(user, cls)
                      else cls.objects.select_for_update().get(pk=user.pk))
            signed = amount if kind in WalletTransaction.CREDIT_KINDS else -amount
            new_balance = _money(wallet.balance_usd + signed)
            if new_balance < 0:
                raise InsufficientBalance(
                    f"Balance is ${wallet.balance_usd}, this needs ${amount}."
                )
            wallet.balance_usd = new_balance
            if signed > 0 and kind != WalletTransaction.Kind.REFUND:
                wallet.topped_up_usd = _money(wallet.topped_up_usd + amount)
            elif signed < 0:
                wallet.spent_usd = _money(wallet.spent_usd + amount)
            wallet.save(update_fields=["balance_usd", "topped_up_usd", "spent_usd", "updated_at"])

            return WalletTransaction.objects.create(
                wallet=wallet, kind=kind, amount_usd=signed, balance_after_usd=new_balance,
                description=description[:200], order=order, balance_topup=balance_topup,
            )

    @classmethod
    def credit(cls, user, amount, *, kind=None, description="", order=None, balance_topup=None):
        return cls._apply(user, kind or WalletTransaction.Kind.TOPUP, amount,
                          description=description, order=order, balance_topup=balance_topup)

    @classmethod
    def debit(cls, user, amount, *, description="", order=None):
        return cls._apply(user, WalletTransaction.Kind.SPEND, amount,
                          description=description, order=order)


class WalletTransaction(models.Model):
    """One movement. Never updated, never deleted -- this is the audit trail."""

    class Kind(models.TextChoices):
        TOPUP = "topup", _("Balance added")
        BONUS = "bonus", _("Bonus credit")
        SPEND = "spend", _("Purchase")
        REFUND = "refund", _("Refund to balance")
        ADJUST = "adjust", _("Manual adjustment")

    CREDIT_KINDS = {Kind.TOPUP, Kind.BONUS, Kind.REFUND, Kind.ADJUST}

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    wallet = models.ForeignKey(Wallet, on_delete=models.CASCADE, related_name="transactions")
    kind = models.CharField(max_length=12, choices=Kind.choices, db_index=True)
    # Signed: positive credits, negative spends. Storing the sign rather than a
    # separate direction column means a SUM over this column is the balance, and
    # a mismatch with Wallet.balance_usd is immediately visible.
    amount_usd = models.DecimalField(max_digits=10, decimal_places=2)
    balance_after_usd = models.DecimalField(max_digits=10, decimal_places=2)
    description = models.CharField(max_length=200, blank=True)
    order = models.ForeignKey("orders.Order", null=True, blank=True, on_delete=models.SET_NULL,
                              related_name="wallet_transactions")
    balance_topup = models.ForeignKey("wallet.BalanceTopUp", null=True, blank=True,
                                      on_delete=models.SET_NULL, related_name="transactions")
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ("-created_at",)
        verbose_name = _("wallet transaction")
        verbose_name_plural = _("wallet transactions")

    def __str__(self):
        return f"{self.kind} {self.amount_usd:+} -> {self.balance_after_usd}"

    @property
    def is_credit(self) -> bool:
        return self.amount_usd > 0


class BalanceTopUp(models.Model):
    """One attempt to add money to a wallet, paid for like any other purchase."""

    class Status(models.TextChoices):
        PENDING = "pending", _("Awaiting payment")
        PAID = "paid", _("Paid")
        CREDITED = "credited", _("Credited")
        FAILED = "failed", _("Failed")
        EXPIRED = "expired", _("Expired")

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    ref = models.CharField(max_length=20, unique=True, db_index=True)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
                             related_name="balance_topups")
    # What the customer pays, what we add on top, and the sum actually credited.
    # All three are stored because a bonus table that changes later must not
    # rewrite what somebody was given at the time.
    amount_usd = models.DecimalField(max_digits=10, decimal_places=2)
    bonus_usd = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal("0.00"))
    credited_usd = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal("0.00"))
    status = models.CharField(max_length=12, choices=Status.choices,
                              default=Status.PENDING, db_index=True)
    # web / ios / android -- so we can see whether the app actually drives credit.
    source = models.CharField(max_length=12, default="web")
    ip = models.GenericIPAddressField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    credited_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ("-created_at",)
        verbose_name = _("balance top-up")
        verbose_name_plural = _("balance top-ups")

    def __str__(self):
        return f"{self.ref} ${self.amount_usd} ({self.status})"

    def save(self, *args, **kwargs):
        if not self.ref:
            self.ref = f"BAL-{uuid.uuid4().hex[:7].upper()}"
        super().save(*args, **kwargs)

    @property
    def total_usd(self) -> Decimal:
        return _money(self.amount_usd + self.bonus_usd)

    def mark_credited(self) -> None:
        self.status = self.Status.CREDITED
        self.credited_usd = self.total_usd
        self.credited_at = timezone.now()
        self.save(update_fields=["status", "credited_usd", "credited_at"])


class ReferralPayout(models.Model):
    """One reward, paid once, for one referred customer.

    The uniqueness constraint on `referred` is the whole safety mechanism: a
    referral pays out exactly once no matter how many times the top-up hook runs,
    and "how many times did that hook run" is not a question anyone should have
    to answer about money.
    """

    referrer = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
                                 related_name="referral_payouts")
    referred = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
                                    related_name="referral_payout")
    amount_usd = models.DecimalField(max_digits=10, decimal_places=2)
    # What the referred customer had topped up when this triggered, so the rule
    # that paid out is visible later even if the threshold changes.
    qualifying_topup_usd = models.DecimalField(max_digits=10, decimal_places=2)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ("-created_at",)
        verbose_name = "referral payout"
        verbose_name_plural = "referral payouts"

    def __str__(self):
        return f"{self.referrer_id} earned ${self.amount_usd} from {self.referred_id}"
