"""Quick provider health check: balance + plan count + registers the webhook URL."""
from django.conf import settings
from django.core.management.base import BaseCommand

from apps.providers.yesim import YesimError, client


class Command(BaseCommand):
    help = "Show Yesim partner balance and optionally register the notification URL."

    def add_arguments(self, parser):
        parser.add_argument("--register-webhook", action="store_true",
                            help="POST /set_notification_url with SITE_URL/webhooks/yesim/<secret>/")

    def handle(self, *args, **opts):
        c = client()
        try:
            bal = c.balance()
            self.stdout.write(f"Balance: {bal.get('balance')} {bal.get('currency')}")
            self.stdout.write(f"Plans: {len(c.plans())}")
        except YesimError as e:
            self.stderr.write(f"Yesim error: {e}")
            return
        if opts["register_webhook"]:
            if not settings.YESIM_WEBHOOK_SECRET:
                self.stderr.write("YESIM_WEBHOOK_SECRET is empty — set it first.")
                return
            url = f"{settings.SITE_URL}/webhooks/yesim/{settings.YESIM_WEBHOOK_SECRET}/"
            self.stdout.write(f"Registering {url} → {c.set_notification_url(url)}")
