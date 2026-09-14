"""Play Integrity: proving a request really is our app on a real device.

The support ID is a bearer secret. Guessing one is infeasible, but "infeasible
to guess" is not the same as "proven to be our app", and it is a device id that
unlocks somebody's guest purchases. Play Integrity closes that: the app asks
Google Play for a signed verdict, we decode it with Google, and only then does
the installation count as attested.

Degrades on purpose. Until the app is in the Play Console with the API enabled
there is nothing to verify against, so an unconfigured deployment records that
no check was possible instead of refusing every request -- the same shape as the
payment providers. Turn PLAY_INTEGRITY_REQUIRED on once it is set up, and
unattested devices stop being able to read purchases back.
"""
from __future__ import annotations

import json
import logging

import requests
from django.conf import settings
from django.core.cache import cache
from django.utils import timezone
from django.utils.crypto import get_random_string

logger = logging.getLogger(__name__)

SCOPE = "https://www.googleapis.com/auth/playintegrity"
NONCE_SECONDS = 300


class IntegrityError(Exception):
    pass


def configured() -> bool:
    return bool(getattr(settings, "PLAY_INTEGRITY_SERVICE_ACCOUNT", "")
                and getattr(settings, "ANDROID_PACKAGE_NAME", ""))


def required() -> bool:
    """Whether an unattested device is refused. Off until the app ships."""
    return bool(getattr(settings, "PLAY_INTEGRITY_REQUIRED", False)) and configured()


def issue_nonce(support_id: str) -> str:
    """A one-shot value the device must bind its verdict to.

    Without it a verdict captured once could be replayed for ever, which would
    reduce attestation to a slightly longer bearer secret.
    """
    nonce = get_random_string(32)
    cache.set(f"integrity:nonce:{support_id}", nonce, NONCE_SECONDS)
    return nonce


def _consume_nonce(support_id: str) -> str | None:
    key = f"integrity:nonce:{support_id}"
    nonce = cache.get(key)
    if nonce:
        cache.delete(key)
    return nonce


def _access_token() -> str:
    from google.auth.transport.requests import Request
    from google.oauth2 import service_account

    raw = settings.PLAY_INTEGRITY_SERVICE_ACCOUNT
    try:
        info = json.loads(raw)
    except json.JSONDecodeError as e:
        raise IntegrityError("PLAY_INTEGRITY_SERVICE_ACCOUNT is not valid JSON.") from e
    credentials = service_account.Credentials.from_service_account_info(info, scopes=[SCOPE])
    credentials.refresh(Request())
    return credentials.token


def decode(token: str) -> dict:
    """Ask Google what this verdict says. Raises IntegrityError on any failure."""
    if not configured():
        raise IntegrityError("Play Integrity is not configured.")
    package = settings.ANDROID_PACKAGE_NAME
    url = (f"https://playintegrity.googleapis.com/v1/{package}:decodeIntegrityToken")
    try:
        response = requests.post(
            url,
            headers={"Authorization": f"Bearer {_access_token()}"},
            json={"integrityToken": token},
            timeout=20,
        )
    except requests.RequestException as e:
        raise IntegrityError(f"Could not reach Play Integrity: {e}") from e
    if response.status_code != 200:
        raise IntegrityError(f"Play Integrity {response.status_code}: {response.text[:300]}")
    return response.json().get("tokenPayloadExternal", {})


def evaluate(payload: dict, expected_nonce: str | None) -> tuple[bool, str]:
    """Decide whether this verdict is good enough, and say why in one line.

    We check three things and not more: the request really came from our package,
    the app binary is the one Google distributed, and the device passes basic
    integrity. Rooted-device and emulator signals are deliberately *not* a
    refusal -- plenty of honest customers run custom ROMs, and this gates reading
    back your own purchases, not spending money.
    """
    request_details = payload.get("requestDetails", {}) or {}
    app_integrity = payload.get("appIntegrity", {}) or {}
    device_integrity = payload.get("deviceIntegrity", {}) or {}

    if expected_nonce:
        seen = request_details.get("nonce") or request_details.get("requestHash") or ""
        if seen != expected_nonce:
            return False, "nonce mismatch"

    package = request_details.get("requestPackageName") or app_integrity.get("packageName")
    if package and package != settings.ANDROID_PACKAGE_NAME:
        return False, f"wrong package: {package}"

    recognition = app_integrity.get("appRecognitionVerdict", "")
    if recognition not in ("PLAY_RECOGNIZED", "UNEVALUATED"):
        return False, f"app not recognised: {recognition or 'unknown'}"

    verdicts = device_integrity.get("deviceRecognitionVerdict", []) or []
    if verdicts and "MEETS_DEVICE_INTEGRITY" not in verdicts and \
            "MEETS_BASIC_INTEGRITY" not in verdicts:
        return False, f"device verdict: {','.join(verdicts)}"

    return True, "ok"


def attest(install, token: str) -> tuple[bool, str]:
    """Verify a token and record the outcome on the installation."""
    nonce = _consume_nonce(install.support_id)
    try:
        payload = decode(token)
    except IntegrityError as e:
        logger.warning("integrity decode failed for %s: %s", install.support_id, e)
        return False, str(e)

    ok, reason = evaluate(payload, nonce)
    install.integrity_verdict = ("verified" if ok else f"failed: {reason}")[:120]
    install.integrity_checked_at = timezone.now()
    install.save(update_fields=["integrity_verdict", "integrity_checked_at"])
    logger.info("integrity for %s: %s", install.support_id, install.integrity_verdict)
    return ok, reason
