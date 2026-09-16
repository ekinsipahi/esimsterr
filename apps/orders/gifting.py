"""Handing an eSIM to the person it was actually bought for.

A gift splits an order in two. The money, the receipt and the refund right stay
with the buyer; the eSIM, the QR code and the data allowance belong to whoever is
travelling. So the profile is addressed to the recipient from the moment it is
issued, and it waits there -- owned by nobody -- until that person proves the
address is theirs.

The same waiting works for an ordinary guest purchase: somebody who bought
without an account and registers a week later finds the eSIM already on their
dashboard instead of writing to support about it.
"""
from __future__ import annotations

import logging

from .models import Esim

log = logging.getLogger(__name__)


def claim_for(user) -> int:
    """Attach every unowned eSIM addressed to this account. Returns how many.

    Called only where the address has just been proved -- opening the emailed
    link, or signing in with Google, which proves it on our behalf. Doing it at
    registration instead would let anyone type a stranger's address and collect
    their eSIM, which is precisely the thing verification exists to stop.
    """
    email = (getattr(user, "email", "") or "").strip()
    if not email or not getattr(user, "email_verified", False):
        return 0
    moved = (Esim.objects
             .filter(user__isnull=True, email__iexact=email, is_deleted=False)
             .update(user=user))
    if moved:
        log.info("Claimed %s eSIM(s) for %s", moved, email)
    return moved
