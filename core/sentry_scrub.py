"""Strip secrets out of anything on its way to Sentry.

Sentry's own filter clears Authorization and Cookie headers and leaves the URL
alone. This project carries secrets in places that filter never looks:

    /webhooks/cron/sync-plans/?token=<CRON_SECRET>   query string
    /verify/<token>/                                 path
    /password-reset/<uidb64>/<token>/                path
    /unsubscribe/?t=<token>                          query string
    X-Admin-Test-Token: <token>                      header — a payment bypass

Any 500 through one of those writes the secret to a third party in plain text,
where it then sits for months. The cron token triggers catalogue syncs; the
admin token grants balance without payment; a password-reset link is an account.

Two layers. The first hides values by parameter or header name. The second
searches for the literal text of the secrets this process actually holds,
wherever it appears -- a log line, an exception message, a breadcrumb, a stack
frame local. The first layer will miss something eventually; the second is the
net under it.
"""
from __future__ import annotations

import json
from urllib.parse import urlsplit, urlunsplit

FILTERED = "[Filtered]"

# A query parameter whose name contains any of these has its value hidden.
_SENSITIVE_PARAM_PARTS = (
    "key", "token", "secret", "pass", "auth", "code", "sig", "sess",
    "nonce", "otp", "hash", "credential", "email", "card", "cvc", "client_secret",
)

# Headers carrying the visitor's real IP. send_default_pii=False does not clear
# these: Sentry only filters headers it recognises as credentials. Behind
# Cloudflare and Render these are where the address actually is, and the privacy
# policy tells customers Sentry receives technical data with identifiers
# stripped -- so they have to go, or that sentence is false.
_PII_HEADERS = frozenset({
    "cf-connecting-ip", "true-client-ip", "x-forwarded-for", "x-real-ip",
    "x-client-ip", "x-cluster-client-ip", "fastly-client-ip", "forwarded",
    "remote-addr",
})

# Headers that are themselves secrets.
_SECRET_HEADERS = frozenset({
    "x-admin-test-token", "stripe-signature", "x-nowpayments-sig",
    "authorization", "cookie", "x-support-id",
})

# Headers whose value is a URL and can therefore carry a secret in its query.
_URL_HEADERS = frozenset({"referer", "referrer", "origin", "location"})

# Paths where the whole thing is a credential. A verification or reset token is
# single-use but, until used, it is a working way into somebody's account.
_SENSITIVE_PATH_PREFIXES = ("/password-reset/", "/verify/")

# Settings holding real secrets, matched as literal text anywhere in the event.
_SECRET_SETTINGS = (
    "DJANGO_SECRET_KEY", "SECRET_KEY", "CRON_SECRET", "ADMIN_TEST_TOKEN",
    "STRIPE_SECRET_KEY", "STRIPE_WEBHOOK_SECRET", "NOWPAYMENTS_API_KEY",
    "NOWPAYMENTS_IPN_SECRET", "RESEND_API_KEY", "ANTHROPIC_API_KEY",
    "SENTRY_AUTH_TOKEN", "GOOGLE_CLIENT_SECRET", "YESIM_API_TOKEN",
    "PLAY_INTEGRITY_SERVICE_ACCOUNT", "DB_PASSWORD",
)

_secret_values: list[str] | None = None


def _known_secrets() -> list[str]:
    """The real secret values, read once and cached.

    Short values are skipped: a three-character secret would match ordinary
    words everywhere and turn every event into redaction soup.
    """
    global _secret_values
    if _secret_values is None:
        from django.conf import settings

        found = []
        for name in _SECRET_SETTINGS:
            value = getattr(settings, name, "") or ""
            if isinstance(value, str) and len(value) >= 8:
                found.append(value)
        _secret_values = sorted(set(found), key=len, reverse=True)
    return _secret_values


def _clean_url(url: str) -> str:
    if not isinstance(url, str) or not url:
        return url
    try:
        parts = urlsplit(url)
    except ValueError:
        return FILTERED

    path = parts.path
    if any(path.startswith(p) for p in _SENSITIVE_PATH_PREFIXES):
        path = path.split("/")[1:2]
        path = "/" + (path[0] if path else "") + "/" + FILTERED

    query = ""
    if parts.query:
        kept = []
        for pair in parts.query.split("&"):
            name, _, value = pair.partition("=")
            low = name.lower()
            kept.append(f"{name}={FILTERED}" if any(p in low for p in _SENSITIVE_PARAM_PARTS)
                        else pair)
        query = "&".join(kept)
    return urlunsplit((parts.scheme, parts.netloc, path, query, ""))


def _clean_headers(headers: dict) -> dict:
    out = {}
    for name, value in headers.items():
        low = str(name).lower()
        if low in _SECRET_HEADERS or low in _PII_HEADERS:
            out[name] = FILTERED
        elif low in _URL_HEADERS:
            out[name] = _clean_url(value)
        else:
            out[name] = value
    return out


def _redact_secrets(blob: str) -> str:
    for secret in _known_secrets():
        if secret and secret in blob:
            blob = blob.replace(secret, FILTERED)
    return blob


def scrub(event, hint=None):
    """sentry_sdk before_send / before_send_transaction hook.

    Never raises. A monitoring hook that throws takes the event with it, and
    losing the error you were trying to record is worse than recording it
    imperfectly.
    """
    try:
        request = event.get("request")
        if isinstance(request, dict):
            if "url" in request:
                request["url"] = _clean_url(request["url"])
            if "query_string" in request:
                request["query_string"] = _clean_url("?" + str(request["query_string"]))[1:]
            if isinstance(request.get("headers"), dict):
                request["headers"] = _clean_headers(request["headers"])
            # The body can hold a password, a card token or an admin token.
            request.pop("data", None)
            request.pop("cookies", None)
            if isinstance(request.get("env"), dict):
                request["env"].pop("REMOTE_ADDR", None)

        # Identify the account, not the person: an id is enough to find the row
        # and does not put an address into a third party's store.
        user = event.get("user")
        if isinstance(user, dict):
            event["user"] = {"id": user.get("id")} if user.get("id") else {}

        # Second layer: the literal secrets, wherever they ended up.
        if _known_secrets():
            serialised = json.dumps(event, default=str)
            if any(s in serialised for s in _known_secrets()):
                event = json.loads(_redact_secrets(serialised))
        return event
    except Exception:  # noqa: BLE001
        return event
