import secrets

from django.conf import settings
from django.db import models


def _ticket_ref():
    alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
    return "T-" + "".join(secrets.choice(alphabet) for _ in range(6))


class Ticket(models.Model):
    class Status(models.TextChoices):
        OPEN = "open", "Open"
        ANSWERED = "answered", "Answered"
        CLOSED = "closed", "Closed"

    class Category(models.TextChoices):
        INSTALL = "install", "Installation / activation"
        CONNECTION = "connection", "No data / connection problem"
        BILLING = "billing", "Payment & refunds"
        ACCOUNT = "account", "Account"
        OTHER = "other", "Something else"

    ref = models.CharField(max_length=10, unique=True, default=_ticket_ref, db_index=True)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True,
                             on_delete=models.SET_NULL, related_name="tickets")
    email = models.EmailField()
    subject = models.CharField(max_length=160)
    category = models.CharField(max_length=16, choices=Category.choices, default=Category.OTHER)
    body = models.TextField()
    iccid = models.CharField(max_length=32, blank=True, help_text="Optional: the eSIM in question")
    order_ref = models.CharField(max_length=12, blank=True)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.OPEN, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.ref} — {self.subject}"


class Reply(models.Model):
    ticket = models.ForeignKey(Ticket, on_delete=models.CASCADE, related_name="replies")
    author = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True,
                               on_delete=models.SET_NULL)
    is_staff_reply = models.BooleanField(default=False)
    body = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]
        verbose_name_plural = "replies"
