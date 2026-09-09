"""Google Identity Services: verify an ID token and return (user, created)."""
from __future__ import annotations

from django.conf import settings
from google.auth.transport import requests as g_requests
from google.oauth2 import id_token

from .models import User


class GoogleAuthError(Exception):
    pass


def user_from_google_token(token: str, signup_ip=None):
    client_id = settings.GOOGLE_CLIENT_ID
    if not client_id:
        raise GoogleAuthError("Google sign-in is not configured.")
    try:
        info = id_token.verify_oauth2_token(token, g_requests.Request(), client_id)
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
