"""Delete the request fingerprint from orders once it has outlived its purpose.

The privacy policy tells customers that the IP address, user agent, browser
language and referrer attached to an order are kept for 24 months and then
deleted. A policy that nothing enforces is not a policy, so this command is what
makes that sentence true. Run it on a schedule (the daily catalogue cron is a
fine place).

Only the fingerprint fields are cleared. The order itself stays: it is an
accounting record, and the customer's own history would otherwise develop holes.
"""
from __future__ import annotations

from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.orders.models import Order

# Card schemes allow disputes up to roughly 18 months out; 24 leaves a margin
# without keeping the data indefinitely. Published in the privacy policy, so
# changing it means changing that page too.
RETENTION_DAYS = 730


class Command(BaseCommand):
    help = "Clear IP, user agent, language and referrer from orders older than the retention window."

    def add_arguments(self, parser):
        parser.add_argument("--days", type=int, default=RETENTION_DAYS)
        parser.add_argument("--dry-run", action="store_true")

    def handle(self, *args, **opts):
        cutoff = timezone.now() - timedelta(days=opts["days"])
        stale = Order.objects.filter(created_at__lt=cutoff).exclude(
            ip__isnull=True, user_agent="", accept_language="", referrer="",
        )
        count = stale.count()

        if opts["dry_run"]:
            self.stdout.write(f"Would clear the fingerprint on {count} order(s) before {cutoff:%Y-%m-%d}")
            return

        stale.update(ip=None, user_agent="", accept_language="", referrer="")
        self.stdout.write(self.style.SUCCESS(
            f"Cleared the request fingerprint on {count} order(s) created before {cutoff:%Y-%m-%d}"
        ))
