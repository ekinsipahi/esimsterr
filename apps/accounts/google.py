"""Google Identity Services: verify an ID token and return (user, created)."""
from __future__ import annotations

from django.conf import settings
from google.auth.transport import requests as g_requests
from google.oauth2 import id_token

from .models import User


class GoogleAuthError(Exception):
    pass


def allowed_audiences() -> list[str]:
    """Which client ids may have issued a token we accept.

    The Android and iOS apps both ask Google for a token addressed to the **web**
    client id -- that is what `setServerClientId` means, and it is why the
    platform client ids never appear in any code. They exist only so Google can
    match a package name and signing certificate to this project.

    Kept as a list anyway: adding a second surface later should be a settings
    change, not a code change, and a wrong audience fails in a way that reads as
    "invalid token" rather than as a configuration problem.
    """
    ids = [settings.GOOGLE_CLIENT_ID, *getattr(settings, "GOOGLE_EXTRA_CLIENT_IDS", [])]
    return [i for i in ids if i]


def user_from_google_token(token: str, signup_ip=None):
    audiences = allowed_audiences()
    if not audiences:
        raise GoogleAuthError("Google sign-in is not configured.")
    try:
        info = id_token.verify_oauth2_token(token, g_requests.Request(), audiences)
    except Exception as e:  # noqa: BLE001
        raise GoogleAuthError(f"Invalid Google token: {e}") from e
    email = (info.get("email") or "").strip().lower()
    if not email:
        raise GoogleAuthError("Google account has no email.")
    user = User.objects.filter(email__iexact=email).first()
    created = False
    if user is None:
        user = User.objects.create_user(
            email=email,
            password=None,
            display_name=(info.get("given_name") or "")[:80],
            email_verified=bool(info.get("email_verified")),
            signup_ip=signup_ip,
        )
        created = True
    elif not user.email_verified and info.get("email_verified"):
        user.email_verified = True
        user.save(update_fields=["email_verified"])
    return user, created
