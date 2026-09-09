"""Refresh usage/status for eSIMs worth polling.

The provider pushes webhooks for status changes and usage milestones, so this is
the safety net: it catches lines whose webhook was missed and keeps the dashboard
counters fresh. Deleted lines and expired plans are skipped — there is nothing
left to learn about them.
"""
from django.core.management.base import BaseCommand
from django.db.models import Q
from django.utils import timezone

from apps.orders.models import Esim
from apps.orders.services import sync_esim
from apps.providers.yesim import YesimError


class Command(BaseCommand):
    help = "Refresh data usage and status for active eSIMs."

    def add_arguments(self, parser):
        parser.add_argument("--limit", type=int, default=200)

    def handle(self, *args, **opts):
        now = timezone.now()
        qs = (
            Esim.objects
            .filter(is_deleted=False)
            .exclude(active_plan_provider_id="")
            # Either the plan has not started yet (no expiry known) or it is still running.
            .filter(Q(plan_expires_at__isnull=True) | Q(plan_expires_at__gt=now))
            .order_by("last_synced_at")[: opts["limit"]]
        )
        ok = err = 0
        for esim in qs:
            try:
                sync_esim(esim)
                ok += 1
            except YesimError as e:
                err += 1
                self.stderr.write(f"{esim.iccid}: {e}")
        self.stdout.write(self.style.SUCCESS(f"Synced {ok}, failed {err}"))
