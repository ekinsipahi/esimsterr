"""The acceptance ledger.

"You accepted our terms" is worth nothing if you cannot say *which* terms. When
a customer disputes a charge six months from now, the question is what the
refund policy said on the day they bought, and the honest answer needs a record
written at the time: the document, its version, a hash of its actual text, and
where the click came from.

One row per document per event, rather than one row listing several, because the
documents version independently and a joint row would have to be rewritten every
time any one of them changed.
"""
from __future__ import annotations

import logging

from django.conf import settings
from django.db import models

logger = logging.getLogger(__name__)


class LegalAcceptance(models.Model):
    class Context(models.TextChoices):
        SIGNUP = "signup", "Sign-up"
        CHECKOUT = "checkout", "Checkout"
        SUBSCRIBE = "subscribe", "Subscription start"
        APP = "app", "Mobile app"
        REACCEPT = "reaccept", "Re-accepted after a change"

    user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True,
                             on_delete=models.SET_NULL, related_name="legal_acceptances")
    # Kept alongside the user because most buyers are guests, and because a
    # closed account must not take the record of what was agreed with it.
    email = models.EmailField(blank=True)
    document = models.CharField(max_length=40)
    # "2026.1+9f2c1a0b3d4e5f60": the human version and the content hash together.
    version = models.CharField(max_length=64)
    surface = models.CharField(max_length=16, default="web")
    context = models.CharField(max_length=16, choices=Context.choices, default=Context.CHECKOUT)
    order_ref = models.CharField(max_length=32, blank=True)
    ip = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.CharField(max_length=400, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        indexes = [
            models.Index(fields=["email", "document"]),
            models.Index(fields=["document", "version"]),
        ]
        ordering = ("-created_at",)

    def __str__(self):
        return f"{self.email or self.user_id} accepted {self.document} {self.version}"


def record_acceptance(request=None, *, user=None, email: str = "",
                      context: str = LegalAcceptance.Context.CHECKOUT,
                      order_ref: str = "", surface: str = "web", documents=None) -> None:
    """Write one row per contract document currently in force.

    Never raises: a failure to write an audit row must not be able to stop a sale
    going through. It is logged instead, which is the right trade -- the money is
    recoverable from Stripe, the customer's patience is not.
    """
    from apps.legal.documents import CONTRACT_DOCUMENTS, BY_SLUG, stamp

    try:
        from core.ratelimit import client_ip
        ip = client_ip(request) if request is not None else None
    except Exception:  # noqa: BLE001
        ip = None

    agent = ""
    if request is not None:
        agent = (request.META.get("HTTP_USER_AGENT") or "")[:400]

    rows = []
    for slug in (documents or CONTRACT_DOCUMENTS):
        doc = BY_SLUG.get(slug)
        if not doc:
            continue
        rows.append(LegalAcceptance(
            user=user if getattr(user, "is_authenticated", False) else None,
            email=(email or getattr(user, "email", "") or "")[:254],
            document=slug, version=stamp(doc, surface), surface=surface,
            context=context, order_ref=order_ref or "", ip=ip, user_agent=agent,
        ))
    try:
        LegalAcceptance.objects.bulk_create(rows)
    except Exception:  # noqa: BLE001
        logger.exception("Could not record legal acceptance (%s, %s)", context, email)
