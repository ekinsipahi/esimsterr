"""Django email backend that sends through the Resend HTTP API."""
from __future__ import annotations

import logging

import requests
from django.conf import settings
from django.core.mail.backends.base import BaseEmailBackend

logger = logging.getLogger(__name__)
RESEND_ENDPOINT = "https://api.resend.com/emails"


class ResendEmailBackend(BaseEmailBackend):
    def __init__(self, fail_silently=False, **kwargs):
        super().__init__(fail_silently=fail_silently, **kwargs)
        self.api_key = getattr(settings, "RESEND_API_KEY", "")

    def send_messages(self, email_messages):
        if not email_messages:
            return 0
        if not self.api_key:
            logger.warning("RESEND_API_KEY not set; dropping %d email(s)", len(email_messages))
            return 0
        sent = 0
        for m in email_messages:
            payload = {
                "from": m.from_email or settings.DEFAULT_FROM_EMAIL,
                "to": list(m.to),
                "subject": m.subject,
                "text": m.body,
            }
            if m.reply_to:
                payload["reply_to"] = list(m.reply_to)
            for content, mimetype in getattr(m, "alternatives", []) or []:
                if mimetype == "text/html":
                    payload["html"] = content
                    break
            try:
                r = requests.post(
                    RESEND_ENDPOINT, json=payload, timeout=20,
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "User-Agent": "esimsterr-mailer/1.0 (+https://esimsterr.com)",
                    },
                )
                if r.status_code >= 400:
                    raise RuntimeError(f"Resend {r.status_code}: {r.text[:300]}")
                sent += 1
            except Exception:  # noqa: BLE001
                logger.exception("Resend send failed")
                if not self.fail_silently:
                    raise
        return sent
