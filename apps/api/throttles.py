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
