"""Hand back coupon seats held by checkouts nobody ever paid for.

A seat is reserved the moment the order is created, and released when the order
visibly dies: the checkout view releases it if the payment provider refuses to
open a session, and the NOWPayments IPN releases it when an invoice expires.
Stripe reports nothing at all when a customer closes the tab on the payment page,
so without this sweeper that order sits PENDING for ever and a capped code slowly
drains through abandoned checkouts.

Safe to run repeatedly: an order is only touched while it is still PENDING, and
release() is itself idempotent.
"""
from __future__ import annotations

from datetime import timedelta

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from apps.orders.models import Order
from apps.payments.models import Payment

from ...services import release

DEFAULT_HOLD_HOURS = 2

# Cancelling an order that can still be paid is far worse than holding a seat a
# few hours longer: fulfilment refuses anything that is not PAID, so the customer
# would be charged and get nothing. Stripe Checkout sessions stay payable for 24
# hours unless an expiry is set, so an order whose payment attempt is younger
# than this is left alone however old the order itself is.
LIVE_SESSION_HOURS = 26
LIVE_PAYMENT_STATUSES = (
    Payment.Status.PENDING,
    Payment.Status.WAITING,
    Payment.Status.CONFIRMING,
    Payment.Status.PARTIAL,
)


def _expire_hold(order_id) -> bool:
    """Release the seat and cancel the order, under the order's own lock."""
    with transaction.atomic():
        order = Order.objects.select_for_update().get(pk=order_id)
        # A webhook may have settled it between the scan and now.
        if order.status != Order.Status.PENDING:
            return False
        release(order)
        order.status = Order.Status.CANCELLED
        order.save(update_fields=["status"])
    return True


class Command(BaseCommand):
    help = "Release coupon seats held by pending orders that were never paid, and cancel them."

    def add_arguments(self, parser):
        parser.add_argument(
            "--hours", type=int, default=DEFAULT_HOLD_HOURS,
            help=f"Age in hours at which an unpaid checkout loses its coupon seat "
                 f"(default {DEFAULT_HOLD_HOURS}).",
        )
        parser.add_argument("--dry-run", action="store_true")

    def handle(self, *args, **opts):
        now = timezone.now()
        cutoff = now - timedelta(hours=opts["hours"])
        session_cutoff = now - timedelta(hours=LIVE_SESSION_HOURS)

        stale = (
            Order.objects
            .filter(status=Order.Status.PENDING,
                    created_at__lt=cutoff,
                    coupon_redemptions__isnull=False)
            .distinct()
            .order_by("created_at")
        )

        released = skipped = 0
        for order in stale:
            if order.payments.filter(
                status__in=LIVE_PAYMENT_STATUSES, created_at__gte=session_cutoff
            ).exists():
                skipped += 1
                continue

            held = order.coupon_code or "coupon"
            if opts["dry_run"]:
                released += 1
                self.stdout.write(
                    f"Would release {held} held by {order.ref} ({order.created_at:%Y-%m-%d %H:%M})"
                )
            elif _expire_hold(order.pk):
                released += 1
                self.stdout.write(f"Released {held} held by {order.ref}")

        verb = "Would release" if opts["dry_run"] else "Released"
        self.stdout.write(self.style.SUCCESS(
            f"{verb} {released} coupon hold(s) older than {opts['hours']}h; "
            f"{skipped} left alone with a payment that can still settle"
        ))
