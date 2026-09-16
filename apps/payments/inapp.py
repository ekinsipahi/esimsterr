"""Paying inside the app, with a card Stripe remembers.

Why this is allowed, since it is the question that decides the architecture: a
mobile data plan is a service consumed outside the app, not content unlocked
inside it. Apple's guideline 3.1.3(e) does not merely permit a non-IAP payment
for that category, it *requires* one -- "you must use purchase methods other
than in-app purchase ... such as Apple Pay or traditional credit card entry".
Google Play's payments policy carries the matching exception for goods and
services consumed outside the app, and every travel eSIM app on Play works this
way.

Card data never reaches this server. The app drives Stripe's PaymentSheet, which
talks to Stripe directly; what comes back here is a customer id and a payment
method id, neither of which can charge anything anywhere else.
"""
from __future__ import annotations

import logging

from django.conf import settings

from . import stripe_client
from .models import Payment

logger = logging.getLogger(__name__)


class InAppError(Exception):
    pass


def enabled() -> bool:
    return bool(getattr(settings, "IN_APP_PAYMENTS", True)
                and stripe_client.configured()
                and settings.STRIPE_PUBLISHABLE_KEY)


def customer_for(*, user=None, install=None, email: str = "") -> tuple[str, object]:
    """The Stripe customer this purchase belongs to, and the row holding its id.

    An account wins over a device: somebody who registers should find the cards
    they saved as a guest, and the claim endpoint moves the id across. A device
    with no account still gets its own customer, because a guest who saved a card
    and cannot use it next time has been given nothing.
    """
    if user is not None and getattr(user, "is_authenticated", False):
        owner, metadata = user, {"user_id": str(user.pk)}
        email = email or user.email
    elif install is not None:
        owner, metadata = install, {"support_id": install.support_id}
    else:
        raise InAppError("No customer to attach this payment to.")

    customer_id = stripe_client.ensure_customer(
        email=email, existing_id=owner.stripe_customer_id, metadata=metadata,
    )
    if owner.stripe_customer_id != customer_id:
        owner.stripe_customer_id = customer_id
        owner.save(update_fields=["stripe_customer_id"])
    return customer_id, owner


def payment_sheet(order, *, customer_id: str, api_version: str, save_card: bool) -> dict:
    """Everything the app needs to open PaymentSheet for this order."""
    if not enabled():
        raise InAppError("In-app payments are not available.")

    payment = Payment.objects.create(
        order=order, user=order.user, provider=Payment.Provider.STRIPE,
        amount_usd=order.amount_usd,
    )
    intent = stripe_client.create_payment_intent(
        amount_usd=order.amount_usd,
        customer_id=customer_id,
        reference=str(payment.id),
        description=f"{settings.SITE_NAME} — {order.plan_title}",
        save_card=save_card,
        email=order.email,
    )
    payment.provider_payment_id = intent["id"]
    payment.status = Payment.Status.WAITING
    payment.raw = {"payment_intent": intent["id"]}
    payment.save(update_fields=["provider_payment_id", "status", "raw"])

    key = stripe_client.ephemeral_key(customer_id, api_version)
    return {
        "payment_intent_client_secret": intent["client_secret"],
        "ephemeral_key": key["secret"],
        "customer_id": customer_id,
        "publishable_key": settings.STRIPE_PUBLISHABLE_KEY,
        "merchant_name": settings.SITE_NAME,
        "order_ref": order.ref,
        "amount_usd": str(order.amount_usd),
        "payment_id": str(payment.id),
    }


def topup_payment_sheet(topup, *, customer_id: str, api_version: str,
                        save_card: bool) -> dict:
    """PaymentSheet for adding balance, so topping up never leaves the app.

    Buying a plan in the app and being sent to a browser to add the credit that
    buys it was the kind of inconsistency that makes people abandon halfway. The
    same rules apply: card details go to Stripe directly, and the webhook credits
    the wallet from the amount Stripe reports actually arriving.
    """
    if not enabled():
        raise InAppError("In-app payments are not available.")

    payment = Payment.objects.create(
        balance_topup=topup, user=topup.user, provider=Payment.Provider.STRIPE,
        amount_usd=topup.amount_usd,
    )
    bonus = f" (+${topup.bonus_usd} bonus)" if topup.bonus_usd else ""
    intent = stripe_client.create_payment_intent(
        amount_usd=topup.amount_usd,
        customer_id=customer_id,
        reference=str(payment.id),
        description=f"{settings.SITE_NAME} — ${topup.amount_usd} balance{bonus}",
        save_card=save_card,
        email=topup.user.email,
    )
    payment.provider_payment_id = intent["id"]
    payment.status = Payment.Status.WAITING
    payment.raw = {"payment_intent": intent["id"]}
    payment.save(update_fields=["provider_payment_id", "status", "raw"])

    key = stripe_client.ephemeral_key(customer_id, api_version)
    return {
        "payment_intent_client_secret": intent["client_secret"],
        "ephemeral_key": key["secret"],
        "customer_id": customer_id,
        "publishable_key": settings.STRIPE_PUBLISHABLE_KEY,
        "merchant_name": settings.SITE_NAME,
        "order_ref": topup.ref,
        "amount_usd": str(topup.amount_usd),
        "bonus_usd": str(topup.bonus_usd),
        "total_usd": str(topup.total_usd),
        "payment_id": str(payment.id),
    }
