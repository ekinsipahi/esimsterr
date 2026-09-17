"""Create the Stripe Product and Price behind every subscribable plan.

These were created lazily, by whoever subscribed first. That works until it does
not: a bug in the Stripe client turned every subscribe into a 500 for days and
nothing noticed, because nothing exercised the path except customers -- who saw
"something broke on our side" and left.

Running it here moves the failure to a place somebody reads. It is idempotent:
the lookup key is derived from the plan, its price in cents and its interval, so
a price that already exists is found rather than duplicated, and a plan whose
price has changed gets a new one while existing subscribers stay on the old.

Nothing is archived. A Stripe price with live subscriptions behind it must
outlive the catalogue entry that created it, and working out which those are is
not worth guessing at from here.
"""
from __future__ import annotations

import time

from django.core.management.base import BaseCommand

from apps.subscriptions.catalogue import subscribable
from apps.subscriptions import stripe_sub


class Command(BaseCommand):
    help = "Ensure every subscribable plan has a Stripe recurring price."

    def add_arguments(self, parser):
        parser.add_argument("--limit", type=int, default=0,
                            help="Stop after this many plans (0 = all).")
        parser.add_argument("--dry-run", action="store_true")

    def handle(self, *args, **opts):
        if not stripe_sub.configured():
            self.stdout.write(self.style.WARNING("Stripe is not configured; nothing to do."))
            return

        # The menu, not every unlimited plan. It used to be the latter, which
        # meant 264 Stripe prices for a product nobody would subscribe to in
        # 245 of those cases.
        plans = subscribable()
        if opts["limit"]:
            plans = plans[:opts["limit"]]

        total = len(plans)
        self.stdout.write(f"{total} subscribable plan(s).")
        if opts["dry_run"]:
            for plan in plans[:20]:
                self.stdout.write(f"  would ensure: {plan.title}")
            return

        done = failed = 0
        errors: list[str] = []
        for i, plan in enumerate(plans, 1):
            try:
                stripe_sub.ensure_price(plan)
                done += 1
            except Exception as e:  # noqa: BLE001
                failed += 1
                errors.append(f"{plan.pk} {plan.title}: {str(e)[:120]}")
            # Gentle on the API: this runs daily and has all night.
            if i % 25 == 0:
                self.stdout.write(f"  {i}/{total}…")
                time.sleep(0.5)

        for line in errors[:10]:
            self.stderr.write(self.style.ERROR(f"  {line}"))
        style = self.style.SUCCESS if not failed else self.style.WARNING
        self.stdout.write(style(f"Stripe prices ready for {done} plan(s), {failed} failed."))
