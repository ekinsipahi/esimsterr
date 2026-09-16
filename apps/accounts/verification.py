"""Proving that an address belongs to whoever typed it.

Signed tokens rather than a table: the token already carries the user id and the
time it was made, Django validates both, and a row that exists only to be
deleted is a row that gets left behind.

An unverified account can be created and can be signed into nowhere -- it holds
no balance, buys nothing and reaches no support channel until the address is
confirmed. The alternative, letting people in and restricting features, means a
mistyped address becomes a customer who cannot be reached about the thing they
bought.
"""
from __future__ import annotations

import logging

from django.conf import settings
from django.core.signing import BadSignature, SignatureExpired, TimestampSigner
from django.urls import reverse
from django.utils import timezone

logger = logging.getLogger(__name__)

SALT = "esimsterr.email-verify"
# Long enough to survive a night's sleep and a spam folder, short enough that a
# forwarded link is not a standing key to the account.
MAX_AGE_SECONDS = 60 * 60 * 48


def make_token(user) -> str:
    return TimestampSigner(salt=SALT).sign(str(user.pk))


def verify_token(token: str):
    """Return the user the token belongs to, or None. Never raises."""
    from .models import User

    try:
        pk = TimestampSigner(salt=SALT).unsign(token, max_age=MAX_AGE_SECONDS)
    except SignatureExpired:
        logger.info("email verification token expired")
        return None
    except (BadSignature, Exception):  # noqa: BLE001
        logger.info("email verification token invalid")
        return None
    return User.objects.filter(pk=pk).first()


def verification_url(user, request=None) -> str:
    path = reverse("verify_email", kwargs={"token": make_token(user)})
    if request is not None:
        return request.build_absolute_uri(path)
    return f"{settings.SITE_URL.rstrip('/')}{path}"


def mark_verified(user) -> None:
    if user.email_verified:
        return
    user.email_verified = True
    user.email_verified_at = timezone.now()
    user.save(update_fields=["email_verified", "email_verified_at"])
    logger.info("Email verified for %s", user.email)
    # Now, and not before: an eSIM bought for this address -- as a gift, or as a
    # guest -- is theirs to manage from here.
    try:
        from apps.orders.gifting import claim_for

        claim_for(user)
    except Exception:  # noqa: BLE001 - never fail a verification over this
        logger.warning("claiming eSIMs for %s failed", user.email, exc_info=True)


def send_verification(user, request=None) -> None:
    from .emails import send_email_bg

    send_email_bg(
        user.email,
        f"Confirm your email to finish setting up {settings.SITE_NAME}",
        "verify_email",
        {"user": user, "verify_url": verification_url(user, request),
         "hours": MAX_AGE_SECONDS // 3600},
    )
