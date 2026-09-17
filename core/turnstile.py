"""Cloudflare Turnstile: a bot check on the forms that cost money to abuse.

WHY IT IS NEEDED HERE. Registering is free, and everything expensive sits one
step behind it. A script that opens accounts all night gets a fresh set of
first-purchase coupon eligibilities, a fresh referral code to point at itself,
and a queue of verification emails sent from our sending domain -- which is how
a domain's reputation gets spent by somebody else. On the sister VPN project one
person ran sixteen cards through checkout in seven minutes; every one of those
was a Radar scan we paid for. Stopping that at the card is already too late.

WHY TURNSTILE AND NOT reCAPTCHA. Cloudflare already fronts this site, so the
visitor is not introduced to a third party they were not already talking to, and
Turnstile sets no cookie and feeds no advertising graph. Our privacy policy tells
customers we do not do that; a Google captcha on the signup form would make that
sentence untrue.

FAIL CLOSED. A network failure talking to Cloudflare refuses the request. A
captcha that opens when it cannot check is not a captcha -- the flood comes back
the moment it breaks, and it breaks exactly when someone is pushing on it. The
cost is that registration stops during a Cloudflare outage, which is the better
of the two outages to have.
"""
from __future__ import annotations

import json
import logging
import urllib.parse
import urllib.request

from django.conf import settings

log = logging.getLogger(__name__)

VERIFY_URL = "https://challenges.cloudflare.com/turnstile/v0/siteverify"
TIMEOUT_SECONDS = 6

# The form field Turnstile's own script writes into the page. Named by
# Cloudflare, not by us.
FIELD = "cf-turnstile-response"


def enabled() -> bool:
    """Off until both keys are set.

    Off rather than broken: a deploy that lands before the keys are entered in
    the dashboard must not be a site where nobody can register. `check_turnstile`
    exists so that state is visible instead of silent.
    """
    return bool(getattr(settings, "TURNSTILE_SECRET_KEY", "")
                and getattr(settings, "TURNSTILE_SITE_KEY", ""))


def verify(token: str, remote_ip: str = "") -> bool:
    if not enabled():
        return True
    token = (token or "").strip()
    if not token:
        return False

    data = {"secret": settings.TURNSTILE_SECRET_KEY, "response": token}
    if remote_ip:
        data["remoteip"] = remote_ip
    request = urllib.request.Request(
        VERIFY_URL,
        data=urllib.parse.urlencode(data).encode(),
        headers={"Content-Type": "application/x-www-form-urlencoded",
                 "User-Agent": "esimsterr-turnstile/1.0 (+https://esimsterr.com)"},
    )
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
            body = json.loads(response.read().decode("utf-8") or "{}")
    except Exception as e:  # noqa: BLE001 — see FAIL CLOSED above
        log.warning("Turnstile unreachable (%s); refusing the request", e)
        return False

    if not body.get("success"):
        log.info("Turnstile rejected a token: %s", body.get("error-codes"))
        return False
    return True


def check(request) -> bool:
    """Verify the token on `request`, keyed on the real caller's address."""
    from core.ratelimit import client_ip

    return verify(request.POST.get(FIELD, ""), client_ip(request))
