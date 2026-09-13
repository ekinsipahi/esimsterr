import uuid

from django.conf import settings
from django.db import models


class Payment(models.Model):
    class Provider(models.TextChoices):
        STRIPE = "stripe", "Stripe (card)"
        NOWPAYMENTS = "nowpayments", "NOWPayments (crypto)"
        MANUAL = "manual", "Manual"

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        WAITING = "waiting", "Waiting for funds"
        CONFIRMING = "confirming", "Confirming"
        PAID = "paid", "Paid"
        PARTIAL = "partially_paid", "Partially paid"
        FAILED = "failed", "Failed"
        EXPIRED = "expired", "Expired"
        REFUNDED = "refunded", "Refunded"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    # Exactly one of these is set. A payment used to always be for an order;
    # adding store credit introduced a second thing a customer can buy, and
    # giving it its own column keeps `settle_payment` a routing decision rather
    # than a guess about what an order-shaped row really meant.
    order = models.ForeignKey("orders.Order", null=True, blank=True,
                              on_delete=models.CASCADE, related_name="payments")
    balance_topup = models.ForeignKey("wallet.BalanceTopUp", null=True, blank=True,
                                      on_delete=models.CASCADE, related_name="payments")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True,
                             on_delete=models.SET_NULL, related_name="payments")

    provider = models.CharField(max_length=20, choices=Provider.choices)
    provider_payment_id = models.CharField(max_length=160, blank=True, db_index=True)
    provider_session_id = models.CharField(max_length=160, blank=True, db_index=True)

    amount_usd = models.DecimalField(max_digits=10, decimal_places=2)
    paid_amount_usd = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True,
                                          help_text="What actually arrived (crypto can underpay)")
    pay_currency = models.CharField(max_length=20, blank=True)
    checkout_url = models.URLField(max_length=1000, blank=True)

    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING, db_index=True)
    settled = models.BooleanField(default=False, help_text="Order was released for fulfilment")
    raw = models.JSONField(default=dict, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "payments"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.get_provider_display()} ${self.amount_usd} — {self.status}"

    @property
    def target(self):
        """What was bought: an Order, or a BalanceTopUp."""
        return self.order or self.balance_topup
