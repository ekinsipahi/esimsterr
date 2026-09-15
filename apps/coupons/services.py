"""Coupon validation, redemption and release.

`validate_coupon` is a read-only check that answers "would this code work, and
for how much" -- safe to call on every keystroke from the checkout page.
`redeem` is the write half and is the only place the counter moves; it takes a
row lock so two people racing the final seat of a capped code cannot both win.

Every rejection carries a machine-readable `reason` alongside its customer-facing
sentence, so a caller can record why a code was refused without parsing prose.

The two identity rules -- once per customer, first order only -- can only be
answered about a person, and answering them for a caller who merely typed an
address into a request body turns a public endpoint into a customer-list oracle.
`preview=True` leaves those two rules out and applies everything else.
"""
from __future__ import annotations

from decimal import Decimal

from django.db import transaction
from django.db.models import F, Q
from django.utils import timezone
from django.utils.translation import gettext as _

from apps.orders.models import Order

from .models import ZERO, Coupon, CouponRedemption, money, normalise_code


class CouponError(Exception):
    """Rejection with a message written for the customer, not the developer."""

    def __init__(self, message, *, reason: str = ""):
        super().__init__(message)
        self.reason = reason


def _identity_filter(user=None, email: str = "") -> Q:
    """Match previous activity by the same person across guest and account checkout."""
    email = (email or "").strip().lower()
    q = Q()
    if user is not None and getattr(user, "is_authenticated", False):
        q |= Q(user=user)
        if getattr(user, "email", ""):
            q |= Q(email=user.email.strip().lower())
    if email:
        q |= Q(email=email)
    return q


def validate_coupon(
    code, *, amount_usd, plan=None, user=None, email="", preview=False, recurring=False
) -> tuple[Coupon, Decimal]:
    """Return (coupon, discount) or raise CouponError with a customer-safe message.

    `recurring=True` refuses outright. A percentage taken off a subscription is
    taken off *every* renewal for as long as it runs, so a code written for a
    one-off sale quietly becomes a permanent margin cut. Subscriptions do not
    offer a coupon field today, but "true because nobody wired it up" is not a
    rule -- this is, and it fails closed if somebody wires it up later.

    `preview=True` is for a page that has not asked for an email address yet -- a
    campaign link such as /checkout/12/?coupon=X landing on checkout. The rules
    that need an identity are skipped so the page can show the indicative
    discount; every other rule still applies, and the full check runs again when
    the order is submitted.
    """
    if recurring:
        raise CouponError(_("Discount codes do not apply to subscriptions."))

    wanted = normalise_code(code)
    if not wanted:
        raise CouponError(_("Enter a coupon code."), reason="empty")

    coupon = Coupon.objects.filter(code=wanted).first()
    if coupon is None:
        raise CouponError(_("We do not recognise that code."), reason="unknown")

    now = timezone.now()
    if not coupon.is_active:
        raise CouponError(_("That code is no longer available."), reason="inactive")
    if coupon.valid_from and coupon.valid_from > now:
        raise CouponError(_("That code is not open yet."), reason="not_started")
    if coupon.valid_until and coupon.valid_until < now:
        raise CouponError(_("That code has expired."), reason="expired")
    if coupon.max_redemptions is not None and coupon.redemptions >= coupon.max_redemptions:
        raise CouponError(_("That code has been fully claimed."), reason="exhausted")

    amount = money(amount_usd)
    if amount <= ZERO:
        raise CouponError(_("There is nothing to discount on this order."), reason="empty_order")
    if coupon.min_order_usd and amount < money(coupon.min_order_usd):
        raise CouponError(
            _("This code needs an order of $%(amount)s or more.")
            % {"amount": money(coupon.min_order_usd)},
            reason="min_order",
        )
    if not coupon.matches_plan(plan):
        raise CouponError(
            _("This code only works on %(scope)s.") % {"scope": coupon.scope_label},
            reason="plan_scope",
        )

    if not preview:
        identity = _identity_filter(user, email)
        if coupon.once_per_customer:
            if not identity:
                raise CouponError(
                    _("Add your email address first, then apply the code."),
                    reason="identity_required",
                )
            if CouponRedemption.objects.filter(identity, coupon=coupon).exists():
                raise CouponError(_("You have already used this code."), reason="already_used")

        if coupon.first_order_only:
            if not identity:
                raise CouponError(
                    _("Add your email address first, then apply the code."),
                    reason="identity_required",
                )
            spent = Order.objects.filter(
                identity, status__in=(Order.Status.PAID, Order.Status.COMPLETED),
            )
            if spent.exists():
                raise CouponError(_("This code is for a first order only."), reason="first_order_only")

    discount = coupon.discount_for(amount, plan=plan)
    if discount <= ZERO:
        raise CouponError(_("This code does not apply to this order."), reason="no_discount")
    return coupon, discount


@transaction.atomic
def redeem(coupon: Coupon, order, *, user=None, email="", ip=None) -> CouponRedemption:
    """Burn one redemption of `coupon` for `order`. Idempotent per order.

    Everything cheap that validate_coupon checked is checked again under
    `select_for_update`, so the last seat of a capped coupon goes to exactly one
    of two racing checkouts and a code switched off mid-checkout is not spent.
    """
    if order is None:
        # Idempotence rests on the (coupon, order) unique constraint, and Postgres
        # treats NULL orders as distinct: a seat with no order could be written
        # twice and could never be released. Caller bug, not a customer message.
        raise ValueError("redeem() needs the order the coupon is being spent on")

    locked = Coupon.objects.select_for_update().get(pk=coupon.pk)

    existing = CouponRedemption.objects.filter(coupon=locked, order=order).first()
    if existing is not None:
        return existing

    if locked.max_redemptions is not None and locked.redemptions >= locked.max_redemptions:
        raise CouponError(_("That code has just been fully claimed."), reason="exhausted")

    # Re-checked under the lock, not only in validate_coupon: two tabs opened at
    # the same moment would otherwise both pass validation and both redeem, and a
    # code the operator switched off or let expire in between would still be spent.
    now = timezone.now()
    if not locked.is_active:
        raise CouponError(_("That code is no longer available."), reason="inactive")
    if locked.valid_from and locked.valid_from > now:
        raise CouponError(_("That code is not open yet."), reason="not_started")
    if locked.valid_until and locked.valid_until < now:
        raise CouponError(_("That code has expired."), reason="expired")

    plan = getattr(order, "plan", None)
    # subtotal_usd is the pre-discount figure, which is what the minimum is about.
    subtotal = money(getattr(order, "subtotal_usd", ZERO))
    if subtotal > ZERO and locked.min_order_usd and subtotal < money(locked.min_order_usd):
        raise CouponError(
            _("This code needs an order of $%(amount)s or more.")
            % {"amount": money(locked.min_order_usd)},
            reason="min_order",
        )
    if not locked.matches_plan(plan):
        raise CouponError(
            _("This code only works on %(scope)s.") % {"scope": locked.scope_label},
            reason="plan_scope",
        )

    identity = _identity_filter(user, email or getattr(order, "email", ""))
    if identity:
        if locked.once_per_customer and CouponRedemption.objects.filter(
            identity, coupon=locked
        ).exists():
            raise CouponError(_("You have already used this code."), reason="already_used")
        if locked.first_order_only and Order.objects.filter(
            identity, status__in=(Order.Status.PAID, Order.Status.COMPLETED),
        ).exists():
            raise CouponError(_("This code is for a first order only."), reason="first_order_only")

    # Checkout stores what it actually took off; the fallback recomputes from the
    # order's pre-discount subtotal, never from order.amount_usd (that is already
    # discounted), falling back to the plan's list price if there is no subtotal.
    discount = getattr(order, "discount_usd", None)
    if discount is None or money(discount) <= ZERO:
        basis = subtotal if subtotal > ZERO else (plan.price if plan is not None else ZERO)
        discount = locked.discount_for(basis, plan=plan)

    Coupon.objects.filter(pk=locked.pk).update(redemptions=F("redemptions") + 1)
    # Keep the caller's in-memory copy honest; it is often rendered right after.
    coupon.redemptions = locked.redemptions + 1

    return CouponRedemption.objects.create(
        coupon=locked,
        order=order,
        user=user if (user is not None and getattr(user, "is_authenticated", False)) else None,
        email=(email or getattr(order, "email", "") or ""),
        ip=ip,
        discount_usd=money(discount),
    )


@transaction.atomic
def release(order) -> None:
    """Give the seat back when an order is cancelled, failed or refunded.

    The redemption row is the seat, so handing the seat back deletes it: a
    once-per-customer code the customer never actually paid for must not go on
    blocking them. What they were offered stays recorded on the order itself
    (coupon_code, discount_usd, email, ip).
    """
    if order is None:
        return
    coupon_ids = sorted(set(
        CouponRedemption.objects.filter(order=order).values_list("coupon_id", flat=True)
    ))
    if not coupon_ids:
        return

    # Same lock order as redeem -- the coupon row first, then its redemptions --
    # so a release racing a redemption queues behind it instead of deadlocking.
    list(Coupon.objects.select_for_update().filter(pk__in=coupon_ids).order_by("pk"))
    rows = list(CouponRedemption.objects.select_for_update().filter(order=order))
    for row in rows:
        # The `gt=0` guard keeps a double release from driving the counter negative.
        Coupon.objects.filter(pk=row.coupon_id, redemptions__gt=0).update(
            redemptions=F("redemptions") - 1
        )
    if rows:
        CouponRedemption.objects.filter(pk__in=[row.pk for row in rows]).delete()


def public_coupons(now=None):
    """Live, listed coupons for the landing page, best offer first."""
    return list(
        Coupon.objects.live(now).public().order_by(
            F("percent_off").desc(nulls_last=True),
            F("amount_off_usd").desc(nulls_last=True),
            "code",
        )
    )
