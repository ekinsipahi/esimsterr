"""Charge the balance subscriptions whose period has run out.

WHY THIS EXISTS. A card subscription is Stripe's problem: Stripe holds the
mandate, decides when to charge and tells us afterwards. A balance subscription
has no mandate anywhere -- the customer's credit is sitting in our own wallet
table -- so somebody has to notice the period ended and take the money. That is
this command, run from cron.

WHY IT IS SAFE TO RUN OFTEN. Every renewal is keyed on a fresh reference and
recorded inside one transaction with the wallet debit, so a run that overlaps
with the previous one cannot bill the same period twice: the first run has
already moved `current_period_end` forward, and the second no longer sees the
subscription as due. Running it every hour is the intended shape.

WHY IT DOES NOT STOP ON A FAILURE. It is a loop over other people's money. One
customer whose balance is short, or one provider call that times out, must not
leave everybody behind them unrenewed -- so each subscription is handled on its
own and the failures are counted and reported at the end.
"""
from __future__ import annotations

import logging

from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.subscriptions.models import Subscription
from apps.subscriptions.services import due_for_renewal, renew_with_balance

log = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Renew balance-funded subscriptions that are due."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run", action="store_true",
            help="List what would be charged without charging anything.")
        parser.add_argument(
            "--limit", type=int, default=0,
            help="Stop after this many subscriptions (0 = no limit).")

    def handle(self, *args, **options):
        now = timezone.now()
        due = due_for_renewal(now)
        if options["limit"]:
            due = due[:options["limit"]]

        renewed = short = failed = 0
        for sub in due:
            label = f"{sub.pk} {sub.user.email} {sub.title} ${sub.price_usd}"
            if options["dry_run"]:
                self.stdout.write(f"would renew  {label}")
                continue
            try:
                cycle = renew_with_balance(sub)
            except Exception as e:                     # noqa: BLE001
                # A provider or database failure, not a short balance. Logged
                # with the subscription id so it can be retried by hand, and the
                # loop carries on: the next customer has done nothing wrong.
                failed += 1
                log.exception("subscription %s failed to renew: %s", sub.pk, e)
                self.stderr.write(self.style.ERROR(f"failed       {label}: {e}"))
                continue

            if cycle is None:
                short += 1
                sub.refresh_from_db(fields=["status"])
                state = ("cancelled" if sub.status == Subscription.Status.CANCELED
                         else "past due")
                self.stdout.write(self.style.WARNING(f"{state:<12} {label}"))
            else:
                renewed += 1
                self.stdout.write(self.style.SUCCESS(f"renewed      {label}"))

        if options["dry_run"]:
            return
        summary = f"{renewed} renewed, {short} short of balance, {failed} failed"
        self.stdout.write(self.style.SUCCESS(summary) if not failed
                          else self.style.ERROR(summary))
