"""Discount coupons and the log of who spent them.

Two facts about this shop shape every decision in here:

* Checkout works without an account, so "one per customer" cannot lean on a user
  row. Each redemption therefore stores the email and the originating IP: for a
  guest that address is the only durable handle we have, and the IP is the weak
  second signal we fall back on when someone works through disposable inboxes.
* A coupon is only ever burned by an order that reached payment. The counter is
  moved inside the same transaction that writes the redemption row (see
  services.redeem) and handed back by services.release when an order dies unpaid,
  so an abandoned checkout never eats the last seat of a capped code. A customer
  who simply closes the payment page tells us nothing, so the seat is also swept
  on a timer: manage.py expire_coupon_holds.
"""
from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal
import re

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext, gettext_lazy as _

CENT = Decimal("0.01")
ZERO = Decimal("0.00")

# A zero-value charge is not a charge: Stripe and NOWPayments both refuse one, so
# an order discounted to nothing cannot be paid at all and the customer is stuck
# on the payment page with no way forward. Every discount therefore leaves at
# least this much payable.
MIN_CHARGE_USD = Decimal("0.50")

# Codes get read off a phone screen and typed back in by hand, so keep them to
# characters that survive that trip.
CODE_PATTERN = re.compile(r"^[A-Z0-9][A-Z0-9-]{1,31}$")


def money(value) -> Decimal:
    """Round to cents the way a customer expects, not the way binary floats do."""
    return Decimal(str(value or 0)).quantize(CENT, rounding=ROUND_HALF_UP)


def normalise_code(code: str) -> str:
    return (code or "").strip().upper().replace(" ", "")


class CouponQuerySet(models.QuerySet):
    def live(self, now=None):
        """Coupons that would be accepted right now, ignoring per-customer rules."""
        now = now or timezone.now()
        return (
            self.filter(is_active=True)
            .filter(models.Q(valid_from__isnull=True) | models.Q(valid_from__lte=now))
            .filter(models.Q(valid_until__isnull=True) | models.Q(valid_until__gte=now))
            .filter(
                models.Q(max_redemptions__isnull=True)
                | models.Q(redemptions__lt=models.F("max_redemptions"))
            )
        )

    def public(self):
        return self.filter(is_public=True)


class Coupon(models.Model):
    class AppliesTo(models.TextChoices):
        ALL = "all", _("Any plan")
        COUNTRY = "country_plans", _("Country plans only")
        REGION = "region_plans", _("Regional plans only")
        UNLIMITED = "unlimited_only", _("Unlimited plans only")

    code = models.CharField(_("code"), max_length=32, unique=True)
    description = models.CharField(
        _("description"), max_length=180, blank=True,
        # Campaign copy: operators rewrite it per campaign from the admin, so it
        # lives in the database rather than in a .po file, where it would go stale
        # the moment it was edited. It is therefore written in the site's default
        # language (the admin says so) and the coupons page marks it with that
        # language, so a translating browser and a screen reader both handle it.
        help_text=_("Shown on the public coupons page. One plain sentence."),
    )

    # Exactly one of these two carries the discount; the pair is guarded by a
    # database constraint as well as clean(), because coupons also arrive from
    # data migrations and the shell where no form validation runs.
    percent_off = models.PositiveSmallIntegerField(
        _("percent off"), null=True, blank=True,
        validators=[MinValueValidator(1), MaxValueValidator(90)],
    )
    amount_off_usd = models.DecimalField(
        _("fixed amount off (USD)"), max_digits=8, decimal_places=2, null=True, blank=True,
    )

    applies_to = models.CharField(
        _("applies to"), max_length=20, choices=AppliesTo.choices, default=AppliesTo.ALL,
    )
    min_order_usd = models.DecimalField(
        _("minimum order (USD)"), max_digits=8, decimal_places=2, default=ZERO,
    )
    max_discount_usd = models.DecimalField(
        _("maximum discount (USD)"), max_digits=8, decimal_places=2, null=True, blank=True,
        help_text=_("Caps a percentage coupon so a large order cannot run away with it."),
    )

    valid_from = models.DateTimeField(_("valid from"), null=True, blank=True)
    valid_until = models.DateTimeField(
        _("valid until"), null=True, blank=True,
        help_text=_("Leave empty for a code with no end date."),
    )

    max_redemptions = models.PositiveIntegerField(
        _("redemption limit"), null=True, blank=True,
        help_text=_("Leave empty for unlimited redemptions."),
    )
    redemptions = models.PositiveIntegerField(_("redemptions used"), default=0, editable=False)
    once_per_customer = models.BooleanField(_("once per customer"), default=True)
    first_order_only = models.BooleanField(_("first order only"), default=False)

    is_active = models.BooleanField(_("active"), default=True, db_index=True)
    is_public = models.BooleanField(
        _("listed publicly"), default=False, db_index=True,
        help_text=_("Public codes appear on the coupons page. Leave off for private codes."),
    )
    stackable = models.BooleanField(
        _("stackable"), default=False,
        help_text=_("Reserved: checkout accepts one code per order."),
    )

    created_at = models.DateTimeField(_("created"), auto_now_add=True)
    updated_at = models.DateTimeField(_("updated"), auto_now=True)

    objects = CouponQuerySet.as_manager()

    class Meta:
        ordering = ("-is_public", "code")
        verbose_name = _("coupon")
        verbose_name_plural = _("coupons")
        indexes = [models.Index(fields=["is_active", "is_public"], name="coupon_live_idx")]
        constraints = [
            models.CheckConstraint(
                condition=(
                    models.Q(percent_off__isnull=False, amount_off_usd__isnull=True)
                    | models.Q(percent_off__isnull=True, amount_off_usd__isnull=False)
                ),
                name="coupon_one_discount_kind",
                violation_error_message=_(
                    "Set either a percentage or a fixed amount, not both and not neither."
                ),
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(percent_off__isnull=True)
                    | models.Q(percent_off__gte=1, percent_off__lte=90)
                ),
                name="coupon_percent_range",
                violation_error_message=_("A percentage coupon must be between 1 and 90."),
            ),
            models.CheckConstraint(
                condition=models.Q(amount_off_usd__isnull=True) | models.Q(amount_off_usd__gt=0),
                name="coupon_amount_positive",
                violation_error_message=_("A fixed discount must be more than zero."),
            ),
        ]

    def __str__(self):
        return f"{self.code} ({self.public_label})"

    def clean(self):
        self.code = normalise_code(self.code)
        if not CODE_PATTERN.match(self.code):
            raise ValidationError({"code": _(
                "Use 2 to 32 characters: letters, digits and dashes, for example BORDERLESS20."
            )})
        if (self.percent_off is None) == (self.amount_off_usd is None):
            raise ValidationError(_(
                "Set either a percentage or a fixed amount off, not both and not neither."
            ))
        if self.percent_off is None and self.max_discount_usd is not None:
            raise ValidationError({"max_discount_usd": _(
                "A cap only makes sense on a percentage coupon."
            )})
        if self.amount_off_usd is not None:
            floor = money(self.amount_off_usd) + MIN_CHARGE_USD
            if money(self.min_order_usd) < floor:
                raise ValidationError({"min_order_usd": _(
                    "A fixed-amount coupon needs a minimum order above the discount, or it "
                    "leaves nothing to charge. Set $%(amount)s or more."
                ) % {"amount": floor}})
        if self.valid_from and self.valid_until and self.valid_until <= self.valid_from:
            raise ValidationError({"valid_until": _("The end date must come after the start date.")})

    def save(self, *args, **kwargs):
        self.code = normalise_code(self.code)
        return super().save(*args, **kwargs)

    # -- state ---------------------------------------------------------------
    def is_live(self, now=None) -> bool:
        """True when the code itself is spendable. Per-customer rules live in services."""
        now = now or timezone.now()
        if not self.is_active:
            return False
        if self.valid_from and self.valid_from > now:
            return False
        if self.valid_until and self.valid_until < now:
            return False
        if self.max_redemptions is not None and self.redemptions >= self.max_redemptions:
            return False
        return True

    @property
    def redemptions_left(self):
        if self.max_redemptions is None:
            return None
        return max(self.max_redemptions - self.redemptions, 0)

    # -- money ---------------------------------------------------------------
    def matches_plan(self, plan) -> bool:
        if self.applies_to == self.AppliesTo.ALL:
            return True
        if plan is None:
            # A restricted coupon cannot be confirmed without knowing the plan;
            # refusing is the only safe direction.
            return False
        if self.applies_to == self.AppliesTo.UNLIMITED:
            return bool(getattr(plan, "is_unlimited", False))
        if self.applies_to == self.AppliesTo.COUNTRY:
            return getattr(plan, "kind", "") == "country"
        if self.applies_to == self.AppliesTo.REGION:
            return getattr(plan, "kind", "") == "region"
        return False

    def discount_for(self, amount_usd, plan=None) -> Decimal:
        """What this coupon takes off `amount_usd`, leaving a payable remainder."""
        amount = money(amount_usd)
        if amount <= ZERO or not self.matches_plan(plan):
            return ZERO
        if self.percent_off:
            discount = money(amount * Decimal(self.percent_off) / Decimal("100"))
            if self.max_discount_usd is not None:
                discount = min(discount, money(self.max_discount_usd))
        else:
            discount = money(self.amount_off_usd)
        # A coupon discounts an order; it never pays money out, and it never
        # discounts down to a total no payment provider will accept. Below
        # MIN_CHARGE_USD there is nothing left to give away, so the code simply
        # does not apply and validate_coupon says so.
        return max(min(discount, amount - MIN_CHARGE_USD), ZERO)

    @property
    def public_label(self) -> str:
        if self.percent_off:
            return gettext("%(percent)s%% off") % {"percent": self.percent_off}
        return gettext("$%(amount)s off") % {"amount": money(self.amount_off_usd)}

    @property
    def scope_label(self) -> str:
        """The restriction as a noun phrase, for a sentence that reads properly."""
        return {
            self.AppliesTo.ALL: gettext("any plan"),
            self.AppliesTo.COUNTRY: gettext("country plans"),
            self.AppliesTo.REGION: gettext("regional plans"),
            self.AppliesTo.UNLIMITED: gettext("unlimited plans"),
        }.get(self.applies_to, gettext("selected plans"))

    @property
    def conditions_label(self) -> str:
        """The small print in one line, for the card and the admin list."""
        bits = []
        if self.min_order_usd and self.min_order_usd > ZERO:
            bits.append(gettext("orders from $%(amount)s") % {"amount": money(self.min_order_usd)})
        if self.applies_to != self.AppliesTo.ALL:
            bits.append(str(self.get_applies_to_display()).lower())
        if self.first_order_only:
            bits.append(gettext("first order only"))
        if self.max_discount_usd is not None:
            bits.append(gettext("up to $%(amount)s off") % {"amount": money(self.max_discount_usd)})
        if self.valid_until:
            bits.append(gettext("until %(date)s") % {"date": self.valid_until.strftime("%d %b %Y")})
        return ", ".join(bits)


class CouponRedemption(models.Model):
    """One seat of a coupon, held by one order.

    The email and IP are recorded because guest checkout leaves no account to
    hang a once-per-customer rule on; for a guest the address is the only durable
    handle we have.

    The row *is* the seat rather than an archive of it: services.release deletes
    it when the order dies unpaid, because a seat handed back must also stop
    blocking that customer from trying the code again. The permanent record of a
    discount that was actually given lives on the order itself (coupon_code,
    discount_usd, email, ip), which release never touches.
    """

    coupon = models.ForeignKey(
        Coupon, on_delete=models.CASCADE, related_name="uses", verbose_name=_("coupon"),
    )
    # SET_NULL, not CASCADE: purging an order row must not quietly hand its seat
    # back. A seat is only ever returned deliberately, through services.release.
    order = models.ForeignKey(
        "orders.Order", null=True, blank=True, on_delete=models.SET_NULL,
        related_name="coupon_redemptions", verbose_name=_("order"),
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="coupon_redemptions", verbose_name=_("account"),
    )
    email = models.EmailField(_("email"), blank=True)
    ip = models.GenericIPAddressField(_("IP address"), null=True, blank=True)
    discount_usd = models.DecimalField(_("discount (USD)"), max_digits=8, decimal_places=2, default=ZERO)
    created_at = models.DateTimeField(_("redeemed"), auto_now_add=True, db_index=True)

    class Meta:
        ordering = ("-created_at",)
        verbose_name = _("coupon redemption")
        verbose_name_plural = _("coupon redemptions")
        indexes = [
            models.Index(fields=["coupon", "email"], name="couponuse_email_idx"),
            models.Index(fields=["coupon", "-created_at"], name="couponuse_recent_idx"),
        ]
        constraints = [
            # Backstop for a retried checkout: one order can only spend a code once.
            # Postgres treats NULL orders as distinct, so this would not catch a
            # duplicate with no order attached -- which is why services.redeem
            # refuses to write one. The column is nullable only for the SET_NULL
            # above, long after the row was created.
            models.UniqueConstraint(
                fields=["coupon", "order"], name="coupon_once_per_order",
            ),
        ]

    def __str__(self):
        return f"{self.coupon_id} -> {self.email or self.user_id or 'anonymous'}"

    def save(self, *args, **kwargs):
        self.email = (self.email or "").strip().lower()
        return super().save(*args, **kwargs)
