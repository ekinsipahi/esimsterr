"""Stripe hosted Checkout: no card data ever touches our servers."""
from __future__ import annotations

from decimal import Decimal

import stripe
from django.conf import settings


class StripeError(Exception):
    pass


def configured() -> bool:
    return bool(settings.STRIPE_SECRET_KEY)


def create_checkout_session(*, amount_usd: Decimal, reference: str, description: str,
                            success_url: str, cancel_url: str, customer_email: str = ""):
    if not configured():
        raise StripeError("Card payments are not available right now. Please pay with crypto.")
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
