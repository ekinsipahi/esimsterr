"""Explicit throttle classes.

DRF's ScopedRateThrottle reads `throttle_scope` off the *view instance*, which a
function-based `@api_view` never exposes — setting the attribute on the decorated
function silently disables throttling instead of erroring. These subclasses carry
the scope themselves, so the limits in REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"]
actually apply.
"""
from rest_framework.throttling import AnonRateThrottle, UserRateThrottle


class AuthAnonThrottle(AnonRateThrottle):
    """Register / login / Google — keyed on IP, since there is no user yet."""
    scope = "auth"


class CheckoutThrottle(UserRateThrottle):
    """Checkout-URL requests from a signed-in app user."""
    scope = "checkout"


class DeviceLookupThrottle(AnonRateThrottle):
    """Guest purchases are read back by device id, which is a bearer secret.

    Guessing one is already infeasible (10^12 of them), but a throttle turns
    "infeasible" into "not worth attempting" and costs a legitimate app nothing:
    it reads its own list a handful of times a session.
    """
    scope = "device_lookup"
    rate = "60/hour"

    def get_cache_key(self, request, view):
        # Keyed on the device id rather than the IP, so one customer on a busy
        # airport NAT cannot throttle everybody else on it.
        support = (request.headers.get("X-Support-Id") or "").strip().upper()
        ident = support or self.get_ident(request)
        return self.cache_format % {"scope": self.scope, "ident": ident}
