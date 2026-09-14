"""Stripe hosted Checkout: no card data ever touches our servers."""
from __future__ import annotations

from decimal import Decimal

import stripe
from django.conf import settings


class StripeError(Exception):
    pass


def configured() -> bool:
    return bool(settings.STRIPE_SECRET_KEY)


def guard_live_key() -> None:
    """Refuse to touch the live Stripe account from a development run.

    This is not hypothetical. Testing the in-app payment endpoint against a
    throwaway SQLite database created a real $4.99 PaymentIntent on the live
    account, because the keys come from .env and .env holds production keys. No
    money moved and it was cancelled a minute later, but it appeared in the
    dashboard with no matching order -- the order was in the scratch database
    and Stripe was not.

    A live key belongs to the environment that owns the live database. If the
    database is SQLite, or DEBUG is on, this process is not that environment.
    Set STRIPE_ALLOW_LIVE_IN_DEBUG to override, deliberately and briefly.
    """
    key = settings.STRIPE_SECRET_KEY
    if not key.startswith("sk_live_"):
        return
    if getattr(settings, "STRIPE_ALLOW_LIVE_IN_DEBUG", False):
        return

    engine = settings.DATABASES["default"]["ENGINE"]
    reason = ("the database is SQLite" if "sqlite" in engine
              else "DEBUG is on" if settings.DEBUG else "")
    if reason:
        raise StripeError(
            f"Refusing to use a live Stripe key when {reason}. Use test keys "
            f"(sk_test_…), or set STRIPE_ALLOW_LIVE_IN_DEBUG=True if you really "
            f"mean to charge the live account from here."
        )


def _api() -> None:
    """Set the key on every call rather than once at import.

    The key comes from the environment, and a module imported before settings
    are fully loaded would otherwise cache an empty string for the process
    lifetime -- which fails as "invalid API key" and sends you looking at
    Stripe rather than at import order.
    """
    if not configured():
        raise StripeError("Card payments are not available right now.")
    guard_live_key()
    stripe.api_key = settings.STRIPE_SECRET_KEY


def create_checkout_session(*, amount_usd: Decimal, reference: str, description: str,
                            success_url: str, cancel_url: str, customer_email: str = ""):
    if not configured():
        raise StripeError("Card payments are not available right now. Please pay with crypto.")
    guard_live_key()
    stripe.api_key = settings.STRIPE_SECRET_KEY
    unit_amount = int((Decimal(amount_usd) * 100).quantize(Decimal("1")))
    params = {
        "mode": "payment",
        "line_items": [{
            "price_data": {
                "currency": "usd",
                "unit_amount": unit_amount,
                "product_data": {"name": description},
            },
            "quantity": 1,
        }],
        "success_url": success_url,
        "cancel_url": cancel_url,
        "client_reference_id": reference,
        "metadata": {"reference": reference},
        "payment_intent_data": {"metadata": {"reference": reference}},
    }
    if customer_email:
        params["customer_email"] = customer_email
        params["payment_intent_data"]["receipt_email"] = customer_email
    try:
        return stripe.checkout.Session.create(**params).to_dict()
    except stripe.error.StripeError as e:  # type: ignore[attr-defined]
        raise StripeError(str(e)) from e


def retrieve_session(session_id: str):
    """Read a Checkout Session back from Stripe.

    This is the return-page fallback: it needs only the secret key, so an order
    still settles when the webhook is late, misconfigured, or the webhook secret
    has not been set at all. Stripe is the authority either way -- we never trust
    the browser's claim that it paid, we go and ask."""
    if not configured():
        raise StripeError("Stripe is not configured.")
    stripe.api_key = settings.STRIPE_SECRET_KEY
    try:
        return stripe.checkout.Session.retrieve(session_id).to_dict()
    except stripe.error.StripeError as e:  # type: ignore[attr-defined]
        raise StripeError(str(e)) from e


def construct_event(payload: bytes, sig_header: str):
    if not settings.STRIPE_WEBHOOK_SECRET:
        raise StripeError("Stripe webhook secret is not configured.")
    return stripe.Webhook.construct_event(payload, sig_header, settings.STRIPE_WEBHOOK_SECRET)


# --- in-app payments ---------------------------------------------------------
# The app pays with Stripe's PaymentSheet, which means card details go straight
# from the device to Stripe and never touch this server. We only ever hold
# customer ids and payment-method ids, which are useless to anyone else.

def ensure_customer(*, email: str, existing_id: str = "", metadata=None) -> str:
    """Find or create the Stripe customer a card will be saved against.

    Keyed to an account where there is one and to the device install where there
    is not, so somebody who buys without registering still gets their card back
    next time -- which is the whole point of saving it.
    """
    _api()
    if existing_id:
        try:
            customer = stripe.Customer.retrieve(existing_id)
            if not getattr(customer, "deleted", False):
                return existing_id
        except stripe.error.StripeError:  # type: ignore[attr-defined]
            pass
    try:
        customer = stripe.Customer.create(email=email or None, metadata=metadata or {})
    except stripe.error.StripeError as e:  # type: ignore[attr-defined]
        raise StripeError(str(e)) from e
    return customer.id


def ephemeral_key(customer_id: str, api_version: str) -> dict:
    """Short-lived key letting the app read that one customer's saved cards.

    The version is whatever the device's Stripe SDK asks for: pass the wrong one
    and PaymentSheet silently shows no saved cards.
    """
    _api()
    try:
        key = stripe.EphemeralKey.create(customer=customer_id, stripe_version=api_version)
    except stripe.error.StripeError as e:  # type: ignore[attr-defined]
        raise StripeError(str(e)) from e
    return {"secret": key.secret, "id": key.id}


def create_payment_intent(*, amount_usd, customer_id: str, reference: str,
                          description: str, save_card: bool, email: str = "") -> dict:
    """A charge the app completes with PaymentSheet.

    `setup_future_usage="off_session"` is what makes the card reusable, and it is
    only sent when the customer asked for that -- storing a card somebody did not
    agree to store is both a bad surprise and a mandate they never gave.
    """
    _api()
    cents = int((Decimal(str(amount_usd)) * 100).quantize(Decimal("1")))
    params = {
        "amount": cents,
        "currency": "usd",
        "customer": customer_id,
        "description": description,
        "metadata": {"reference": reference},
        "automatic_payment_methods": {"enabled": True},
    }
    if email:
        params["receipt_email"] = email
    if save_card:
        params["setup_future_usage"] = "off_session"
    try:
        intent = stripe.PaymentIntent.create(**params)
    except stripe.error.StripeError as e:  # type: ignore[attr-defined]
        raise StripeError(str(e)) from e
    return {"id": intent.id, "client_secret": intent.client_secret}


def list_cards(customer_id: str) -> list[dict]:
    """Saved cards, in the shape the app shows them. Never raises: a settings
    screen that cannot reach Stripe should say "no cards", not crash."""
    if not customer_id:
        return []
    _api()
    try:
        methods = stripe.PaymentMethod.list(customer=customer_id, type="card")
    except stripe.error.StripeError:  # type: ignore[attr-defined]
        return []
    out = []
    for method in methods.auto_paging_iter():
        card = getattr(method, "card", None)
        if card is None:
            continue
        out.append({
            "id": method.id,
            "brand": card.brand,
            "last4": card.last4,
            "exp_month": card.exp_month,
            "exp_year": card.exp_year,
        })
    return out


def detach_card(payment_method_id: str) -> None:
    _api()
    try:
        stripe.PaymentMethod.detach(payment_method_id)
    except stripe.error.StripeError as e:  # type: ignore[attr-defined]
        raise StripeError(str(e)) from e


def card_belongs_to(payment_method_id: str, customer_id: str) -> bool:
    """Never detach a card on somebody's say-so alone."""
    if not (payment_method_id and customer_id):
        return False
    _api()
    try:
        method = stripe.PaymentMethod.retrieve(payment_method_id)
    except stripe.error.StripeError:  # type: ignore[attr-defined]
        return False
    return getattr(method, "customer", None) == customer_id
