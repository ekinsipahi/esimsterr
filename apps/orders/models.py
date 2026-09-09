import secrets
import uuid
from decimal import Decimal

from django.conf import settings
from django.db import models
from django.urls import reverse
from django.utils import timezone


def _ref():
    """Short customer-facing reference: ES-XXXXXXX (no sequential id leak)."""
    alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
    return "ES-" + "".join(secrets.choice(alphabet) for _ in range(7))


class Order(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Awaiting payment"
        PAID = "paid", "Paid — provisioning"
        COMPLETED = "completed", "Completed"
        FAILED = "failed", "Failed"
        REFUNDED = "refunded", "Refunded"
        CANCELLED = "cancelled", "Cancelled"

    class Kind(models.TextChoices):
        NEW = "new", "New eSIM"
        TOPUP = "topup", "Top-up"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    ref = models.CharField(max_length=12, unique=True, default=_ref, db_index=True)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True,
                             on_delete=models.SET_NULL, related_name="orders")
    # Guest checkout is allowed; the email is where the QR code goes.
    email = models.EmailField()

    kind = models.CharField(max_length=10, choices=Kind.choices, default=Kind.NEW)
    plan = models.ForeignKey("catalog.Plan", null=True, on_delete=models.SET_NULL, related_name="orders")
    # Frozen copies so a later catalogue change never rewrites history.
    plan_title = models.CharField(max_length=180)
    plan_provider_id = models.CharField(max_length=64)
    plan_days = models.PositiveIntegerField(default=0)
    plan_data_label = models.CharField(max_length=32, blank=True)

    amount_usd = models.DecimalField(max_digits=10, decimal_places=2)
    cost_amount = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal("0"))
    cost_currency = models.CharField(max_length=3, default="EUR")
    currency = models.CharField(max_length=3, default="USD")

    status = models.CharField(max_length=12, choices=Status.choices, default=Status.PENDING, db_index=True)
    # Top-ups attach to an eSIM the customer already owns.
    target_esim = models.ForeignKey("orders.Esim", null=True, blank=True,
                                    on_delete=models.SET_NULL, related_name="topups")

    fulfillment_error = models.TextField(blank=True)
    fulfillment_attempts = models.PositiveIntegerField(default=0)

    created_at = models.DateTimeField(auto_now_add=True)
    paid_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    ip = models.GenericIPAddressField(null=True, blank=True)

    class Meta:
        db_table = "orders"
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["status", "created_at"])]

    def __str__(self):
        return f"{self.ref} · {self.plan_title} · {self.status}"

    def get_absolute_url(self):
        return reverse("order_detail", kwargs={"ref": self.ref})

    @property
    def margin_usd(self):
        eur_usd = Decimal(str(settings.EUR_USD_RATE))
        cost_usd = self.cost_amount * (eur_usd if self.cost_currency == "EUR" else Decimal("1"))
        return (self.amount_usd - cost_usd).quantize(Decimal("0.01"))

    @property
    def is_payable(self):
        return self.status == self.Status.PENDING

    def mark_paid(self):
        if self.status == self.Status.PENDING:
            self.status = self.Status.PAID
            self.paid_at = timezone.now()
            self.save(update_fields=["status", "paid_at"])


class Esim(models.Model):
    """A provisioned eSIM profile. One row per ICCID we ever hand to a customer."""

    class Status(models.TextChoices):
        RELEASED = "Released", "Ready to install"
        INSTALLED = "Installed", "Installed"
        ENABLED = "Enabled", "Active"
        DISABLED = "Disabled", "Disabled"
        DELETED = "Deleted", "Removed from device"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True,
                             on_delete=models.SET_NULL, related_name="esims")
    email = models.EmailField(blank=True)
    order = models.ForeignKey(Order, null=True, blank=True, on_delete=models.SET_NULL,
                              related_name="esims")

    provider = models.CharField(max_length=20, default="yesim")
    iccid = models.CharField(max_length=32, unique=True, db_index=True)
    provider_esim_id = models.CharField(max_length=32, blank=True)
    provider_user_id = models.CharField(max_length=32, blank=True)

    # Activation payload (LPA string is what the QR encodes).
    lpa_code = models.CharField(max_length=255, blank=True)
    ios_tap_link = models.URLField(max_length=500, blank=True)
    esim_passport_url = models.URLField(max_length=500, blank=True)
    apn = models.CharField(max_length=32, blank=True)
    imsi = models.CharField(max_length=32, blank=True)
    msisdn = models.CharField(max_length=32, blank=True)

    label = models.CharField(max_length=80, blank=True, help_text="Customer-visible nickname")
    status_qr = models.CharField(max_length=16, choices=Status.choices, default=Status.RELEASED)

    active_plan_provider_id = models.CharField(max_length=64, blank=True)
    plan_title = models.CharField(max_length=180, blank=True)
    is_unlimited = models.BooleanField(default=False)
    plan_activated_at = models.DateTimeField(null=True, blank=True)
    plan_expires_at = models.DateTimeField(null=True, blank=True)

    data_package_mb = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    data_used_mb = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    data_left_mb = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    network_info = models.JSONField(default=dict, blank=True)

    is_deleted = models.BooleanField(default=False)
    last_synced_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "esims"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.iccid} ({self.plan_title or 'no plan'})"

    def get_absolute_url(self):
        return reverse("esim_detail", kwargs={"pk": self.pk})

    # ---- presentation ------------------------------------------------------
    @property
    def display_name(self):
        return self.label or self.plan_title or f"eSIM ···{self.iccid[-6:]}"

    @property
    def data_used_pct(self):
        if self.is_unlimited or not self.data_package_mb:
            return None
        pct = (self.data_used_mb or 0) / self.data_package_mb * 100
        return min(100, round(float(pct)))

    @property
    def data_left_gb(self):
        if self.data_left_mb is None:
            return None
        return round(float(self.data_left_mb) / 1024, 2)

    @property
    def data_package_gb(self):
        if self.data_package_mb is None:
            return None
        return round(float(self.data_package_mb) / 1024, 2)

    @property
    def days_left(self):
        if not self.plan_expires_at:
            return None
        delta = self.plan_expires_at - timezone.now()
        return max(0, delta.days)

    @property
    def is_expired(self):
        return bool(self.plan_expires_at and self.plan_expires_at < timezone.now())

    @property
    def is_active(self):
        return bool(self.active_plan_provider_id) and not self.is_expired and not self.is_deleted

    @property
    def android_manual(self):
        """Android's manual entry splits the LPA string into SM-DP+ address + activation code."""
        parts = (self.lpa_code or "").split("$")
        if len(parts) >= 3:
            return {"smdp": parts[1], "code": parts[2]}
        return None


class WebhookEvent(models.Model):
    """Raw provider notifications (EsimStatus, PackageUsage, expiry) for audit + replay."""

    source = models.CharField(max_length=20, default="yesim")
    event_type = models.CharField(max_length=40, blank=True, db_index=True)
    iccid = models.CharField(max_length=32, blank=True, db_index=True)
    payload = models.JSONField(default=dict)
    processed = models.BooleanField(default=False)
    error = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.source}:{self.event_type} {self.iccid}"
