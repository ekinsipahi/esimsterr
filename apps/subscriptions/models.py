"""Recurring subscriptions for unlimited plans.

An unlimited plan is a duration, not a data bucket, so it is the one product
that naturally repeats: the customer wants the same line to stay alive month
after month without thinking about it. Everything financial still lands in
orders.Order — a subscription cycle is simply an Order that Stripe triggered —
so revenue, margin and fulfilment keep one reporting surface and one code path.
"""
from __future__ import annotations

import uuid
from decimal import Decimal

from django.conf import settings
from django.db import models
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext_lazy as _


class Subscription(models.Model):
    """One auto-renewing unlimited plan, tied to one eSIM line."""

    class Status(models.TextChoices):
        ACTIVE = "active", _("Active")
        PAST_DUE = "past_due", _("Payment failed")
        CANCELED = "canceled", _("Cancelled")
        INCOMPLETE = "incomplete", _("Awaiting first payment")
        PAUSED = "paused", _("Paused")

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    # Required, unlike one-off checkout: a recurring charge needs somewhere to
    # manage and cancel it, and that is an account.
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
                             related_name="subscriptions", verbose_name=_("customer"))
    plan = models.ForeignKey("catalog.Plan", on_delete=models.PROTECT,
                             related_name="subscriptions", verbose_name=_("plan"))
    # The line this subscription keeps alive. Empty until the first cycle is
    # provisioned; every later cycle tops this same eSIM up, so the customer
    # never reinstalls a profile.
    esim = models.ForeignKey("orders.Esim", null=True, blank=True, on_delete=models.SET_NULL,
                             related_name="subscriptions", verbose_name=_("eSIM"))

    stripe_customer_id = models.CharField(max_length=64, blank=True, db_index=True)
    # NULL rather than "" while the Checkout session is still open: several
    # abandoned attempts would otherwise collide on the unique constraint.
    stripe_subscription_id = models.CharField(max_length=64, null=True, blank=True,
                                              unique=True, db_index=True)
    stripe_price_id = models.CharField(max_length=64, blank=True)

    status = models.CharField(max_length=12, choices=Status.choices,
                              default=Status.INCOMPLETE, db_index=True, verbose_name=_("status"))
    price_usd = models.DecimalField(max_digits=10, decimal_places=2,
                                    verbose_name=_("price per cycle (USD)"))
    interval_days = models.PositiveIntegerField(
        default=30, verbose_name=_("billing interval (days)"),
        help_text=_("Mirrors the plan duration: 7, 15 or 30 days."))
    current_period_end = models.DateTimeField(null=True, blank=True,
                                              verbose_name=_("renews on"))
    cancel_at_period_end = models.BooleanField(default=False,
                                               verbose_name=_("cancels at period end"))

    started_at = models.DateTimeField(null=True, blank=True)
    canceled_at = models.DateTimeField(null=True, blank=True)
    renewals_count = models.PositiveIntegerField(default=0)
    last_error = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "subscriptions"
        ordering = ["-created_at"]
        verbose_name = _("subscription")
        verbose_name_plural = _("subscriptions")
        indexes = [models.Index(fields=["status", "current_period_end"])]

    def __str__(self):
        return f"{self.user_id} · {self.title} · {self.status}"

    def get_absolute_url(self):
        return reverse("subscription_detail", kwargs={"pk": self.pk})

    # ---- presentation ------------------------------------------------------
    @property
    def is_live(self):
        """Billing and connectivity are both healthy. `past_due` is deliberately
        excluded: the card failed, so the customer needs to act, not relax."""
        return self.status == self.Status.ACTIVE

    @property
    def needs_attention(self):
        return self.status == self.Status.PAST_DUE

    @property
    def days_until_renewal(self):
        if not self.current_period_end:
            return None
        return max(0, (self.current_period_end - timezone.now()).days)

    @property
    def target(self):
        return self.plan.target if self.plan_id else None

    @property
    def target_name(self):
        return self.plan.target_name if self.plan_id else ""

    @property
    def title(self):
        return self.plan.title if self.plan_id else ""

    @property
    def interval_label(self):
        if self.interval_days == 7:
            return _("week")
        if self.interval_days == 30:
            return _("month")
        return _("%(days)s days") % {"days": self.interval_days}


class SubscriptionCycle(models.Model):
    """One billed period. Deduplicated on the Stripe invoice id so a webhook
    retry can never provision (or charge for) the same period twice."""

    class Status(models.TextChoices):
        PAID = "paid", _("Paid")
        FAILED = "failed", _("Failed")

    subscription = models.ForeignKey(Subscription, on_delete=models.CASCADE,
                                     related_name="cycles", verbose_name=_("subscription"))
    stripe_invoice_id = models.CharField(max_length=80, unique=True, db_index=True)
    period_start = models.DateTimeField(null=True, blank=True)
    period_end = models.DateTimeField(null=True, blank=True)
    amount_usd = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal("0"),
                                     verbose_name=_("amount (USD)"))
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PAID,
                              db_index=True, verbose_name=_("status"))
    # Every paid cycle creates a real Order, so margin reporting, fulfilment and
    # the customer's order history need no special case for subscriptions.
    order = models.ForeignKey("orders.Order", null=True, blank=True, on_delete=models.SET_NULL,
                              related_name="subscription_cycles", verbose_name=_("order"))
    error = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "subscription_cycles"
        ordering = ["-created_at"]
        verbose_name = _("subscription cycle")
        verbose_name_plural = _("subscription cycles")

    def __str__(self):
        return f"{self.stripe_invoice_id} · ${self.amount_usd}"
