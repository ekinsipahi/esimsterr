"""Admin test tool: walk the real purchase flow without paying for it.

One hole, not several. Rather than adding a bypass to every payment path, this
grants balance and settles an order directly -- everything else is the ordinary
code: the same order builder, the same coupon validation, the same provisioning,
the same device binding. A test that avoids the real path proves nothing about
the real path.

Guarded by ADMIN_TEST_TOKEN, which is empty by default. A payment bypass that
ships enabled is a bypass somebody else finds. Every use is logged at warning
level with what it did and to whom, and every order it creates is flagged
`is_test` so it never reaches a revenue figure or a sale alert.

Provisioning is real by default: the point is to prove the whole chain works,
including the provider. Pass provision=false to stop before that if you only
want to exercise the app.
"""
from __future__ import annotations

import hmac
import logging

from django.conf import settings

logger = logging.getLogger(__name__)


def enabled() -> bool:
    return bool(getattr(settings, "ADMIN_TEST_TOKEN", ""))


def authorised(request) -> bool:
    """Constant-time compare, so the token cannot be discovered a byte at a time."""
    if not enabled():
        return False
    supplied = (request.headers.get("X-Admin-Test-Token")
                or request.data.get("token") or "")
    return hmac.compare_digest(str(supplied), settings.ADMIN_TEST_TOKEN)


def note(action: str, **detail) -> None:
    logger.warning("ADMIN TEST TOOL: %s %s", action,
                   " ".join(f"{k}={v}" for k, v in detail.items()))
