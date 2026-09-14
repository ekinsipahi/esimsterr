"""Stripe Billing layer for subscriptions.

Self-bootstrapping: we never hand-maintain Products and Prices in the Stripe
dashboard. A Price is looked up by a deterministic `lookup_key` derived from the
plan, and created on first use. The key carries the amount and the interval, so
repricing a plan mints a new Price instead of silently charging the old amount
forever — the alternative (a stable key whose amount drifts from the catalogue)
is the kind of bug that only surfaces on a customer's statement.
"""
from __future__ import annotations

import logging
import re
from decimal import Decimal

import stripe

from apps.payments.stripe_client import guard_live_key
from django.conf import settings

log = logging.getLogger(__name__)

# Module-level memo: a warm process resolves a repeat subscribe without a
# round-trip. Cleared naturally on deploy, which is also when prices change.
_PRICE_CACHE: dict[str, str] = {}


class SubscriptionError(Exception):
    pass


def configured() -> bool:
    return bool(settings.STRIPE_SECRET_KEY)


def _api():
    if not configured():
        raise SubscriptionError("Card payments are not available right now.")
    guard_live_key()
    stripe.api_key = settings.STRIPE_SECRET_KEY


def _safe(value) -> str:
    return re.sub(r"[^A-Za-z0-9]+", "_", str(value or "")).strip("_").lower()


def _lookup_key(plan, cents: int, recurring: dict) -> str:
    return (f"esimsterr_sub_{_safe(plan.provider_plan_id)}_{cents}c_"
            f"{recurring['interval']}{recurring['interval_count']}")[:200]


def _product_id(plan) -> str:
    return f"esimsterr_plan_{_safe(plan.provider_plan_id)}"[:64]


def _ensure_product(plan) -> str:
    pid = _product_id(plan)
    try:
        return stripe.Product.retrieve(pid)["id"]
    except stripe.InvalidRequestError:
        pass
    try:
        return stripe.Product.create(
            id=pid,
            name=f"{settings.SITE_NAME} — {plan.target_name} unlimited, {plan.days} days",
            metadata={"plan_id": str(plan.pk), "provider_plan_id": str(plan.provider_plan_id)},
        )["id"]
    except stripe.InvalidRequestError:
        # Lost a race with a concurrent subscribe; the product now exists.
        return stripe.Product.retrieve(pid)["id"]


def ensure_price(plan) -> str:
    """Return the Stripe recurring Price id for `plan`, creating it if needed."""
    # Imported here, not at module scope: services owns the pricing rules and
    # imports this module, so a top-level import would be circular.
    from .services import stripe_interval, subscription_price

    _api()
    amount: Decimal = subscription_price(plan)
    cents = int((amount * 100).quantize(Decimal("1")))
    recurring = stripe_interval(plan.days)
    key = _lookup_key(plan, cents, recurring)

    cached = _PRICE_CACHE.get(key)
    if cached:
        return cached

    try:
        # stripe-python v15 returns a ListObject here, not a dict. Calling
        # .get() on one raises, which is what turned every attempt to subscribe
        # into a 500. The rows live on .data.
        found = stripe.Price.list(lookup_keys=[key], active=True, limit=1)
        rows = list(found.data or [])
        if rows:
            _PRICE_CACHE[key] = rows[0]["id"]
            return rows[0]["id"]

        price = stripe.Price.create(
            currency="usd",
            unit_amount=cents,
            product=_ensure_product(plan),
            recurring=recurring,
            lookup_key=key,
            nickname=f"{plan.target_name} unlimited · {plan.days}d subscription",
            metadata={"plan_id": str(plan.pk), "provider_plan_id": str(plan.provider_plan_id),
                      "interval_days": str(plan.days)},
        )
    except stripe.InvalidRequestError as e:
        # A parallel request may have claimed the lookup key between our list
        # and our create. Read it back rather than minting a duplicate Price.
        rows = list(stripe.Price.list(lookup_keys=[key], active=True, limit=1).data or [])
        if rows:
            _PRICE_CACHE[key] = rows[0]["id"]
            return rows[0]["id"]
        raise SubscriptionError(str(e)) from e
    except stripe.StripeError as e:
        raise SubscriptionError(str(e)) from e

    _PRICE_CACHE[key] = price["id"]
    return price["id"]


def create_checkout_session(user, plan, success_url: str, cancel_url: str, *,
                            subscription_id=None, price_id: str = "") -> dict:
    """Hosted Checkout in subscription mode. No card data touches our servers."""
    _api()
    price = price_id or ensure_price(plan)
    reference = str(subscription_id or "")
    metadata = {
        "subscription_id": reference,
        "plan_id": str(plan.pk),
        "provider_plan_id": str(plan.provider_plan_id),
    }
    params = {
        "mode": "subscription",
        "line_items": [{"price": price, "quantity": 1}],
        "success_url": success_url,
        "cancel_url": cancel_url,
        "client_reference_id": reference,
        "metadata": metadata,
        # Mirrored onto the Subscription so every later invoice webhook can find
        # its way home even if the Checkout session is long gone.
        "subscription_data": {"metadata": metadata},
        # No allow_promotion_codes: a Stripe-dashboard promotion code would be a
        # second discount channel that apps.coupons cannot see — no Coupon row,
        # no redemption cap, no coupon_code on the order — and it would stack on
        # top of the subscription discount, which can price a renewal below cost.
        # Discounts belong to apps.coupons: one ledger, one cap.
    }
    if getattr(user, "email", ""):
        params["customer_email"] = user.email
    try:
        return stripe.checkout.Session.create(**params).to_dict()
    except stripe.StripeError as e:
        raise SubscriptionError(str(e)) from e


def billing_portal_url(customer_id: str, return_url: str) -> str:
    """Self-serve card update, invoice history and cancellation."""
    _api()
    if not customer_id:
        raise SubscriptionError("This subscription has no billing account yet.")
    try:
        session = stripe.billing_portal.Session.create(customer=customer_id,
                                                       return_url=return_url)
    except stripe.StripeError as e:
        raise SubscriptionError(str(e)) from e
    # Also a StripeObject rather than a dict: attribute access, not .get().
    url = getattr(session, "url", "") or ""
    if not url:
        raise SubscriptionError("Stripe did not return a billing portal URL.")
    return url


def retrieve_subscription(stripe_subscription_id: str) -> dict:
    _api()
    try:
        return stripe.Subscription.retrieve(stripe_subscription_id).to_dict()
    except stripe.StripeError as e:
        raise SubscriptionError(str(e)) from e


def cancel_at_period_end(stripe_subscription_id: str, cancel: bool = True) -> dict:
    """Used by admin/support; customers cancel through the billing portal."""
    _api()
    try:
        return stripe.Subscription.modify(stripe_subscription_id,
                                          cancel_at_period_end=bool(cancel)).to_dict()
    except stripe.StripeError as e:
        raise SubscriptionError(str(e)) from e


def cancel_now(stripe_subscription_id: str) -> dict:
    """Stop a subscription immediately, not at the end of the period.

    Used when an account is deleted: "cancel at period end" would leave one more
    charge to land on a customer who no longer has anywhere to see it. A
    subscription Stripe has already lost track of is treated as cancelled --
    there is nothing left that could bill.
    """
    _api()
    try:
        return stripe.Subscription.cancel(stripe_subscription_id).to_dict()
    except stripe.InvalidRequestError as e:
        if "No such subscription" in str(e) or "canceled" in str(e).lower():
            return {"status": "canceled"}
        raise SubscriptionError(str(e)) from e
    except stripe.StripeError as e:
        raise SubscriptionError(str(e)) from e
