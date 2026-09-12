"""Support surface: the ticket system (email-backed, guest-friendly) and the
AI assistant chat (account-only).

Two deliberate shapes here:

* A ticket is NOT tied to an account. Checkout works without one, so a guest who
  cannot connect abroad must be able to reach us with nothing but the address
  they bought with. Access to a guest thread is gated on a signed token that
  only reaches the buyer's inbox (see `access_token`), never on the reference
  alone -- refs are short and guessable.
* A conversation IS tied to an account. Every POST there spends money on an LLM
  call, so the endpoint requires a login rather than relying on the widget being
  hidden.
"""
from __future__ import annotations

import secrets
import uuid as uuidlib

from django.conf import settings
from django.core import signing
from django.db import models
from django.urls import reverse
from django.utils.translation import gettext_lazy as _

# Unambiguous alphabet: no O/0, no I/1 -- refs get read aloud on the phone and
# typed back from a screenshot.
_REF_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"

TICKET_TOKEN_SALT = "support.ticket.access"
# Long enough that a traveller who only reads mail on Wi-Fi once a fortnight can
# still open their thread when they get home.
TICKET_TOKEN_MAX_AGE = 60 * 60 * 24 * 90


def _ticket_ref() -> str:
    return "T-" + "".join(secrets.choice(_REF_ALPHABET) for _ in range(6))


class Ticket(models.Model):
    class Status(models.TextChoices):
        OPEN = "open", _("Open")
        ANSWERED = "answered", _("Answered")
        CLOSED = "closed", _("Closed")

    class Category(models.TextChoices):
        INSTALL = "install", _("Installation and activation")
        CONNECTION = "connection", _("No data or connection problem")
        BILLING = "billing", _("Payments and billing")
        REFUND = "refund", _("Refund request")
        ACCOUNT = "account", _("Account")
        OTHER = "other", _("Something else")

    id = models.BigAutoField(primary_key=True)
    ref = models.CharField(_("reference"), max_length=10, unique=True,
                           default=_ticket_ref, db_index=True)
    # SET_NULL, not CASCADE: a deleted account must not erase the paper trail of
    # a refund conversation.
    user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True,
                             on_delete=models.SET_NULL, related_name="tickets",
                             verbose_name=_("account"))
    email = models.EmailField(_("email"))
    subject = models.CharField(_("subject"), max_length=160)
    category = models.CharField(_("category"), max_length=16,
                                choices=Category.choices, default=Category.OTHER)
    status = models.CharField(_("status"), max_length=10, choices=Status.choices,
                              default=Status.OPEN, db_index=True)
    order_ref = models.CharField(_("order reference"), max_length=12, blank=True)
    iccid = models.CharField(_("ICCID"), max_length=32, blank=True)
    ip = models.GenericIPAddressField(_("IP address"), null=True, blank=True)
    user_agent = models.CharField(_("user agent"), max_length=300, blank=True)
    created_at = models.DateTimeField(_("opened"), auto_now_add=True)
    updated_at = models.DateTimeField(_("last activity"), auto_now=True, db_index=True)

    class Meta:
        ordering = ("-updated_at",)
        verbose_name = _("ticket")
        verbose_name_plural = _("tickets")
        indexes = [
            models.Index(fields=["user", "-updated_at"]),
            models.Index(fields=["email", "-updated_at"]),
        ]

    def __str__(self):
        return f"{self.ref} [{self.status}] {self.subject[:40]}"

    @staticmethod
    def new_ref() -> str:
        return _ticket_ref()

    # -- guest access -------------------------------------------------------
    @property
    def access_token(self) -> str:
        """Signed proof of ownership, emailed to the buyer.

        The ticket reference is only six characters; on its own it is a guess
        away from exposing someone else's ICCID and order history. The address
        is signed in as well and checked on the way back in, so a token that
        leaked -- a forwarded email, a screenshot -- stops opening the thread
        as soon as the address on the ticket is corrected.
        """
        return signing.dumps({"ref": self.ref, "email": self.email},
                             salt=TICKET_TOKEN_SALT)

    @staticmethod
    def check_token(token: str, ref: str, email: str) -> bool:
        """`email` is the address currently on the ticket; a token signed for an
        older address no longer opens it."""
        try:
            data = signing.loads(token or "", salt=TICKET_TOKEN_SALT,
                                 max_age=TICKET_TOKEN_MAX_AGE)
        except Exception:  # noqa: BLE001 - bad, tampered or expired all mean "no"
            return False
        if not isinstance(data, dict) or data.get("ref") != ref:
            return False
        return (data.get("email") or "").strip().lower() == (email or "").strip().lower()

    def get_absolute_url(self) -> str:
        return reverse("ticket_detail", args=[self.ref])

    @property
    def guest_url(self) -> str:
        return f"{self.get_absolute_url()}?t={self.access_token}"

    @property
    def is_closed(self) -> bool:
        return self.status == self.Status.CLOSED


class TicketMessage(models.Model):
    class Role(models.TextChoices):
        USER = "user", _("Customer")
        STAFF = "staff", _("Support team")

    id = models.BigAutoField(primary_key=True)
    ticket = models.ForeignKey(Ticket, on_delete=models.CASCADE, related_name="messages",
                               verbose_name=_("ticket"))
    role = models.CharField(_("written by"), max_length=8, choices=Role.choices,
                            default=Role.USER)
    body = models.TextField(_("message"))
    created_at = models.DateTimeField(_("sent"), auto_now_add=True, db_index=True)

    class Meta:
        ordering = ("created_at",)
        verbose_name = _("ticket message")
        verbose_name_plural = _("ticket messages")
        indexes = [models.Index(fields=["ticket", "created_at"])]

    def __str__(self):
        return f"{self.ticket.ref} {self.role}: {self.body[:40]}"

    @property
    def is_staff(self) -> bool:
        return self.role == self.Role.STAFF


class AssistantConversation(models.Model):
    """One live chat thread. Login-only: see the module docstring."""

    class Status(models.TextChoices):
        OPEN = "open", _("Open")
        ESCALATED = "escalated", _("Escalated")
        CLOSED = "closed", _("Closed")

    id = models.UUIDField(primary_key=True, default=uuidlib.uuid4, editable=False)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
                             related_name="assistant_conversations",
                             verbose_name=_("account"))
    status = models.CharField(_("status"), max_length=12, choices=Status.choices,
                              default=Status.OPEN, db_index=True)
    # Comma-joined intent flags seen across the thread; a plain string so the
    # admin can filter on it without a join.
    intent_flags = models.CharField(_("intent flags"), max_length=120, blank=True, default="")
    # An operator took over: the AI stops answering and the human writes.
    owner_joined = models.BooleanField(_("operator joined"), default=False)
    user_unread = models.PositiveSmallIntegerField(_("unread for customer"), default=0)
    ip = models.GenericIPAddressField(_("IP address"), null=True, blank=True)
    user_agent = models.CharField(_("user agent"), max_length=300, blank=True)
    escalated_at = models.DateTimeField(_("escalated"), null=True, blank=True)
    created_at = models.DateTimeField(_("started"), auto_now_add=True)
    updated_at = models.DateTimeField(_("last activity"), auto_now=True, db_index=True)

    class Meta:
        ordering = ("-updated_at",)
        verbose_name = _("assistant conversation")
        verbose_name_plural = _("assistant conversations")
        indexes = [models.Index(fields=["user", "-updated_at"])]

    def __str__(self):
        return f"Chat {self.user_id} [{self.status}] {self.intent_flags}"[:60]

    def add_flags(self, flags) -> None:
        current = {f for f in self.intent_flags.split(",") if f}
        current |= {str(f) for f in flags}
        self.intent_flags = ",".join(sorted(current))[:120]

    @property
    def flag_list(self) -> list:
        return [f for f in self.intent_flags.split(",") if f]


class AssistantMessage(models.Model):
    class Role(models.TextChoices):
        USER = "user", _("Customer")
        ASSISTANT = "assistant", _("Assistant")
        OWNER = "owner", _("Support team")

    id = models.UUIDField(primary_key=True, default=uuidlib.uuid4, editable=False)
    conversation = models.ForeignKey(AssistantConversation, on_delete=models.CASCADE,
                                     related_name="messages", verbose_name=_("conversation"))
    role = models.CharField(_("written by"), max_length=10, choices=Role.choices)
    content = models.TextField(_("message"))
    intent = models.CharField(_("intent"), max_length=60, blank=True, default="")
    created_at = models.DateTimeField(_("sent"), auto_now_add=True, db_index=True)

    class Meta:
        ordering = ("created_at",)
        verbose_name = _("assistant message")
        verbose_name_plural = _("assistant messages")
        indexes = [models.Index(fields=["conversation", "created_at"])]

    def __str__(self):
        return f"{self.role}: {self.content[:50]}"
