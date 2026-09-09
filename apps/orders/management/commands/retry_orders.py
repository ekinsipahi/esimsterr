"""Provision paid-but-unfulfilled orders (provider outage, empty partner balance...)."""
from django.core.management.base import BaseCommand

from apps.orders.services import retry_failed


class Command(BaseCommand):
    help = "Retry fulfilment for orders stuck in the paid state."

    def add_arguments(self, parser):
        parser.add_argument("--limit", type=int, default=20)

    def handle(self, *args, **opts):
        ok, failed = retry_failed(limit=opts["limit"])
        self.stdout.write(self.style.SUCCESS(f"Provisioned {ok}, still failing {failed}"))
