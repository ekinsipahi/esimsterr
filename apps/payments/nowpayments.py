"""NOWPayments hosted invoice + IPN signature verification (HMAC-SHA512)."""
from __future__ import annotations

import hashlib
import hmac
import json

import requests
from django.conf import settings


class NowPaymentsError(Exception):
    pass


def configured() -> bool:
    return bool(settings.NOWPAYMENTS_API_KEY)


def _session():
    s = requests.Session()
    s.headers.update({"x-api-key": settings.NOWPAYMENTS_API_KEY,
                      "Content-Type": "application/json"})
    return s


def create_invoice(*, amount_usd, reference: str, description: str,
                   success_url: str, cancel_url: str, ipn_url: str) -> dict:
    if not configured():
        raise NowPaymentsError("Crypto payments are not available right now.")
    base = settings.NOWPAYMENTS_API_BASE.rstrip("/")
    try:
        r = _session().post(f"{base}/invoice", timeout=30, json={
            "price_amount": float(amount_usd),
            "price_currency": "usd",
            "order_id": reference,
            "order_description": description,
            "ipn_callback_url": ipn_url,
            "success_url": success_url,
            "cancel_url": cancel_url,
        })
    except requests.RequestException as e:
        raise NowPaymentsError(f"NOWPayments request failed: {e}") from e
    if r.status_code >= 400:
        raise NowPaymentsError(f"NOWPayments {r.status_code}: {r.text[:300]}")
    return r.json()


def verify_ipn_signature(raw_body: bytes, signature: str) -> bool:
    """Signature is HMAC-SHA512 over the JSON body with keys sorted alphabetically."""
    secret = settings.NOWPAYMENTS_IPN_SECRET
    if not secret or not signature:
        return False
    try:
        payload = json.loads(raw_body.decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        return False
    msg = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    expected = hmac.new(secret.encode(), msg.encode(), hashlib.sha512).hexdigest()
    return hmac.compare_digest(expected, signature)
