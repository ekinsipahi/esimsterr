"""In-app inbox: messages the operator sends, that customers read in the app.

A push notification is gone the moment it is swiped away. An inbox is where the
offer still is an hour later, when they are actually at the airport. The two are
meant to work together -- the push is the tap on the shoulder, this is the thing
being pointed at -- so a message is written once here and a push carries its
title.

Marketing consent is enforced at the query, not at the send. Anything marked
promotional is simply invisible to a customer who opted out, which is a rule
that cannot be forgotten by whoever writes the next campaign.
"""
from __future__ import annotations

from django.conf import settings
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _


class InboxMessage(models.Model):
    class Kind(models.TextChoices):
        PROMO = "promo", _("Offer")
        NEWS = "news", _("News")
        SYSTEM = "system", _("Service message")

    class Audience(models.TextChoices):
        EVERYONE = "all", _("Everyone")
        HAS_ESIM = "has_esim", _("Customers with an eSIM")
        NO_PURCHASE = "no_purchase", _("Signed up, never bought")
        HAS_BALANCE = "has_balance", _("Customers holding balance")
        NO_BALANCE = "no_balance", _("Customers with no balance")

    title = models.CharField(_("title"), max_length=90,
                             help_text=_("Shown in the list and used as the push title. Keep it short."))
    body = models.TextField(_("body"), max_length=1200)
    kind = models.CharField(max_length=10, choices=Kind.choices, default=Kind.PROMO, db_index=True)
    audience = models.CharField(max_length=16, choices=Audience.choices, default=Audience.EVERYONE)

    # Optional call to action. A relative path is resolved against the site, so
    # a campaign can point at a destination page without hardcoding the host.
    cta_label = models.CharField(max_length=40, blank=True)
    cta_url = models.CharField(max_length=300, blank=True,
                               help_text=_("Absolute URL, or a path like /esim/japan/"))
    coupon_code = models.CharField(max_length=40, blank=True,
                                   help_text=_("Shown as a copyable code in the message."))

    is_published = models.BooleanField(default=False, db_index=True)
    publish_at = models.DateTimeField(default=timezone.now, db_index=True)
    expires_at = models.DateTimeField(null=True, blank=True,
                                      help_text=_("After this it disappears from every inbox."))

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("-publish_at",)
        verbose_name = _("inbox message")
        verbose_name_plural = _("inbox messages")

    def __str__(self):
        return f"[{self.get_kind_display()}] {self.title}"

    @property
    def is_marketing(self) -> bool:
        """Offers and news are marketing; a service message is not.

        The distinction decides who may receive it, so it is derived from the
        kind rather than left as a checkbox somebody forgets to tick."""
        return self.kind in (self.Kind.PROMO, self.Kind.NEWS)

    @property
    def is_live(self) -> bool:
        now = timezone.now()
        return (self.is_published and self.publish_at <= now
                and (self.expires_at is None or self.expires_at > now))

    def absolute_cta(self) -> str:
        if not self.cta_url:
            return ""
        if self.cta_url.startswith("http"):
            return self.cta_url
        return f"{settings.SITE_URL.rstrip('/')}/{self.cta_url.lstrip('/')}"

    @classmethod
    def for_user(cls, user):
        """Everything this customer may see, newest first."""
        now = timezone.now()
        qs = cls.objects.filter(is_published=True, publish_at__lte=now).filter(
            models.Q(expires_at__isnull=True) | models.Q(expires_at__gt=now)
        )
        if not getattr(user, "marketing_opt_in", True):
            qs = qs.filter(kind=cls.Kind.SYSTEM)

        audience = cls.Audience
        exclude = []
        has_esim = user.esims.filter(is_deleted=False).exists()
        has_orders = user.orders.exists()
        balance = getattr(getattr(user, "wallet", None), "balance_usd", 0) or 0
        if not has_esim:
            exclude.append(audience.HAS_ESIM)
        if has_orders:
            exclude.append(audience.NO_PURCHASE)
        if balance <= 0:
            exclude.append(audience.HAS_BALANCE)
        else:
            exclude.append(audience.NO_BALANCE)
        if exclude:
            qs = qs.exclude(audience__in=exclude)
        return qs


class InboxRead(models.Model):
    """Per-customer read state. Absence means unread, so nothing is written
    until somebody actually opens a message."""

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
                             related_name="inbox_reads")
    message = models.ForeignKey(InboxMessage, on_delete=models.CASCADE, related_name="reads")
    read_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=("user", "message"), name="uniq_inbox_read"),
        ]
        verbose_name = "inbox read"
        verbose_name_plural = "inbox reads"

    def __str__(self):
        return f"{self.user_id} read {self.message_id}"
