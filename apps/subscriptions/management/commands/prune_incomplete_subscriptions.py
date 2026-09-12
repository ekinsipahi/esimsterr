"""Delete subscription attempts that never reached Stripe.

Opening the subscribe page and walking away from Stripe Checkout leaves an
INCOMPLETE Subscription row behind. The view reuses a recent one, but an
attempt abandoned weeks ago is dead weight: it clutters the admin, it skews any
count of subscriptions, and it can never become live because no Stripe
subscription was ever attached to it. Run this alongside the other daily crons.

Only rows that never reached Stripe are touched. A row that has a Stripe
subscription id is Stripe's business: it either pays, or Stripe expires it and
the customer.subscription.updated webhook marks it cancelled here.
"""
from __future__ import annotations

from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.subscriptions.models import Subscription

# Stripe Checkout sessions expire after 24 hours, so a day-old row can no longer
# be completed. A week gives support time to see what the customer tried to do.
STALE_DAYS = 7


class Command(BaseCommand):
    help = "Delete abandoned INCOMPLETE subscriptions that never reached Stripe."

    def add_arguments(self, parser):
        parser.add_argument("--days", type=int, default=STALE_DAYS)
        parser.add_argument("--dry-run", action="store_true")

    def handle(self, *args, **opts):
        cutoff = timezone.now() - timedelta(days=opts["days"])
        stale = Subscription.objects.filter(
            status=Subscription.Status.INCOMPLETE,
            stripe_subscription_id__isnull=True,
            created_at__lt=cutoff,
            cycles__isnull=True,
        )
        count = stale.count()

        if opts["dry_run"]:
            self.stdout.write(
                f"Would delete {count} abandoned subscription attempt(s) "
                f"created before {cutoff:%Y-%m-%d}")
            return

        # Delete by primary key: the cycles__isnull join makes the queryset a
        # join, which delete() cannot run directly.
        Subscription.objects.filter(pk__in=list(stale.values_list("pk", flat=True))).delete()
        self.stdout.write(self.style.SUCCESS(
            f"Deleted {count} abandoned subscription attempt(s) created before {cutoff:%Y-%m-%d}"
        ))
