"""Is the bot check actually on?

Turnstile is off when its keys are unset, deliberately: a deploy that lands
before somebody pastes the keys in must not be a site nobody can register on.
The cost of that decision is that "off" and "working" look identical from the
outside, so this says which one it is -- and proves the secret key is the one
Cloudflare has, rather than a typo that will fail closed on every real visitor.
"""
import json
import urllib.parse
import urllib.request

from django.conf import settings
from django.core.management.base import BaseCommand

from core import turnstile


class Command(BaseCommand):
    help = "Report whether Cloudflare Turnstile is configured and reachable."

    def add_arguments(self, parser):
        parser.add_argument(
            "--strict", action="store_true",
            help="Exit non-zero when the bot check is not protecting anything.",
        )

    def handle(self, *args, **options):
        if not turnstile.enabled():
            self.stdout.write(self.style.WARNING(
                "Turnstile is OFF — registration, sign-in and password reset are "
                "unprotected. Set TURNSTILE_SITE_KEY and TURNSTILE_SECRET_KEY."))
            if options["strict"]:
                raise SystemExit(1)
            return

        # A made-up token. Cloudflare answers "invalid-input-response", which is
        # the answer we want: it proves the secret was accepted and the endpoint
        # is reachable. A bad secret comes back as "invalid-input-secret"
        # instead, and that is the failure worth catching before a customer does.
        data = urllib.parse.urlencode({
            "secret": settings.TURNSTILE_SECRET_KEY,
            "response": "check-turnstile-not-a-real-token",
        }).encode()
        try:
            request = urllib.request.Request(
                turnstile.VERIFY_URL, data=data,
                headers={"Content-Type": "application/x-www-form-urlencoded"})
            with urllib.request.urlopen(request, timeout=turnstile.TIMEOUT_SECONDS) as response:
                body = json.loads(response.read().decode("utf-8") or "{}")
        except Exception as e:  # noqa: BLE001
            self.stdout.write(self.style.ERROR(
                f"Turnstile is configured but unreachable: {e}. Every sign-up and "
                f"sign-in is being refused right now."))
            raise SystemExit(1) from e

        codes = body.get("error-codes") or []
        if "invalid-input-secret" in codes or "missing-input-secret" in codes:
            self.stdout.write(self.style.ERROR(
                f"Cloudflare does not recognise TURNSTILE_SECRET_KEY ({codes}). "
                f"Every sign-up and sign-in is being refused right now."))
            raise SystemExit(1)

        self.stdout.write(self.style.SUCCESS(
            "Turnstile is ON, the secret is accepted and Cloudflare answered."))
