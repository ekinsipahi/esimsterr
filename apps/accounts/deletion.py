"""Closing an account, properly.

The old implementation deactivated the user and rewrote their email. That is
enough to make the login stop working and nothing else: an active Stripe
subscription kept renewing against a customer who no longer had a dashboard to
cancel it from, and every support ticket and assistant conversation stayed
readable. Deleting an account has to stop the money first.

Order and payment rows survive, with the customer's identity unlinked and the
request fingerprint erased. Tax law requires an invoice record, and GDPR Article
17(3)(b) is the exception that permits keeping it; everything not covered by
that goes.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field

from django.db import transaction
from django.utils import timezone

logger = logging.getLogger(__name__)


class DeletionBlocked(Exception):
    """Raised when we cannot guarantee the customer stops being charged."""


@dataclass
class DeletionReport:
    subscriptions_cancelled: int = 0
    tickets_deleted: int = 0
    conversations_deleted: int = 0
    orders_unlinked: int = 0
    esims_unlinked: int = 0
    fingerprints_cleared: int = 0

    def as_lines(self) -> list:
        return [
            f"subscriptions cancelled: {self.subscriptions_cancelled}",
            f"orders unlinked: {self.orders_unlinked}",
            f"eSIM lines unlinked: {self.esims_unlinked}",
            f"request fingerprints cleared: {self.fingerprints_cleared}",
            f"support tickets deleted: {self.tickets_deleted}",
            f"assistant conversations deleted: {self.conversations_deleted}",
        ]


def active_subscriptions(user):
    from apps.subscriptions.models import Subscription
    return Subscription.objects.filter(
        user=user,
        status__in=[Subscription.Status.ACTIVE, Subscription.Status.PAST_DUE,
                    Subscription.Status.INCOMPLETE, Subscription.Status.PAUSED],
    )


def _cancel_subscriptions(user, report: DeletionReport) -> None:
    """Stop every recurring charge before anything else is touched.

    If Stripe refuses, the deletion is abandoned rather than completed. A closed
    account with a live subscription behind it is a customer being charged with
    no way left to stop it, which is worse than an account that did not close.
    """
    from apps.subscriptions.models import Subscription
    from apps.subscriptions.stripe_sub import SubscriptionError, cancel_now

    for sub in active_subscriptions(user):
        if sub.stripe_subscription_id:
            try:
                cancel_now(sub.stripe_subscription_id)
            except SubscriptionError as e:
                logger.warning("Cannot cancel %s while deleting account %s: %s",
                               sub.stripe_subscription_id, user.pk, e)
                raise DeletionBlocked(
                    "We could not cancel your active subscription with our payment "
                    "processor, so we have not deleted the account — you would have "
                    "gone on being charged. Please contact support and we will do both."
                ) from e
        sub.status = Subscription.Status.CANCELED
        sub.cancel_at_period_end = False
        sub.canceled_at = timezone.now()
        sub.save(update_fields=["status", "cancel_at_period_end", "canceled_at"])
        report.subscriptions_cancelled += 1


def delete_account(user) -> DeletionReport:
    """Erase what we can, unlink what we must keep, and stop the billing."""
    from apps.orders.models import Esim, Order
    from apps.support.models import AssistantConversation, Ticket

    report = DeletionReport()
    _cancel_subscriptions(user, report)

    with transaction.atomic():
        report.conversations_deleted = AssistantConversation.objects.filter(user=user).delete()[0]
        report.tickets_deleted = Ticket.objects.filter(user=user).delete()[0]

        orders = Order.objects.filter(user=user)
        report.fingerprints_cleared = orders.exclude(
            ip__isnull=True, user_agent="", accept_language="", referrer="",
        ).count()
        report.orders_unlinked = orders.update(
            user=None, ip=None, user_agent="", accept_language="", referrer="",
        )
        report.esims_unlinked = Esim.objects.filter(user=user).update(user=None)

        user.is_active = False
        user.email = f"deleted-{user.pk}@deleted.invalid"
        user.set_unusable_password()
        fields = ["is_active", "email", "password"]
        for name, blank in (("display_name", ""), ("google_sub", ""),
                            ("marketing_opt_in", False)):
            if hasattr(user, name):
                setattr(user, name, blank)
                fields.append(name)
        user.save(update_fields=fields)

    logger.info("Deleted account %s: %s", user.pk, "; ".join(report.as_lines()))
    return report
