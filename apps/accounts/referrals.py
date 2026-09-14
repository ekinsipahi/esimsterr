"""Applying a referral code to an account.

Kept out of the views because three places need it -- web sign-up, app
registration, and entering a code afterwards -- and the rules about who may
claim a referral are exactly the kind that drift when they are written three
times.
"""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


class ReferralError(Exception):
    """Something the customer should be told, in words they can act on."""


def apply_referral_code(user, code: str | None, *, strict: bool = False):
    """Attach `user` to whoever owns `code`.

    Returns the referrer, or None when there is nothing to do. With `strict` the
    reasons for refusing are raised instead of swallowed, which is what the
    "enter a code" screen needs and what sign-up does not: a bad code typed at
    registration must never cost somebody their account.
    """
    from .models import User

    code = (code or "").strip().upper()
    if not code:
        if strict:
            raise ReferralError("Enter a referral code.")
        return None

    if user.referred_by_id is not None:
        if strict:
            raise ReferralError("You already used a referral code.")
        return None

    referrer = User.objects.filter(referral_code__iexact=code, is_active=True).first()
    if referrer is None:
        if strict:
            raise ReferralError("We do not recognise that code.")
        return None

    if referrer.pk == user.pk:
        if strict:
            raise ReferralError("You cannot refer yourself.")
        return None

    # A code applied once a customer is established is not a referral; it is
    # somebody claiming credit for a customer they did not bring.
    if user.orders.exists():
        if strict:
            raise ReferralError("Referral codes only apply before your first order.")
        return None

    user.referred_by = referrer
    user.save(update_fields=["referred_by"])
    logger.info("Referral: %s was referred by %s", user.email, referrer.email)
    return referrer
