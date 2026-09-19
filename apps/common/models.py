"""Switches the app obeys, changeable without a store release.

THE PROBLEM THIS SOLVES. A bug on the website is fixed in the time it takes to
deploy. A bug in a shipped app is fixed when Google finishes reviewing the next
release and then when each customer's phone gets round to updating -- days, and
for some of them never. In between, the broken thing keeps being broken in front
of everybody who opens the app.

So the app asks the server what it is allowed to do, every time it starts. If
card payments break, they can be switched off here and the app falls back to
balance in seconds. If a release ships something dangerous, a minimum version
sends those installs to the store instead of letting them carry on. If the
provider is down, a banner says so in the customer's own app rather than leaving
them to find out at an airport.

None of these are features. They are the handle you reach for when something has
already gone wrong, and the time to fit a handle is before that.
"""
from __future__ import annotations

from django.core.cache import cache
from django.db import models
from django.utils.translation import gettext_lazy as _

CACHE_KEY = "remote-config"
CACHE_SECONDS = 60


class RemoteConfig(models.Model):
    """One row, edited in the admin, read by every app start."""

    class Notice(models.TextChoices):
        INFO = "info", _("Information")
        WARNING = "warning", _("Warning")
        CRITICAL = "critical", _("Serious problem")

    singleton = models.PositiveSmallIntegerField(primary_key=True, default=1, editable=False)

    # --- the blunt instruments ------------------------------------------
    maintenance = models.BooleanField(
        _("maintenance mode"), default=False,
        help_text=_("Blocks the app with the message below. For an outage bad enough "
                    "that letting people try to buy would only take their money into "
                    "a broken system."))
    maintenance_message = models.CharField(
        _("maintenance message"), max_length=300, blank=True,
        default="We are fixing a problem and will be back shortly. Nothing you have "
                "bought is affected.")
    min_supported_version = models.CharField(
        _("minimum app version"), max_length=12, default="1.0.0",
        help_text=_("Installs older than this are sent to the store instead of "
                    "being allowed to continue. Raise it only for a release that "
                    "fixes something the old one gets wrong with money or data."))

    # --- saying something without blocking anything ---------------------
    notice_message = models.CharField(
        _("notice"), max_length=300, blank=True,
        help_text=_("Shown as a banner at the top of the app. Empty means no banner."))
    notice_level = models.CharField(_("notice level"), max_length=10,
                                    choices=Notice.choices, default=Notice.INFO)
    notice_url = models.URLField(_("notice link"), blank=True)
    notice_cta = models.CharField(_("notice button"), max_length=40, blank=True)

    # --- feature switches ------------------------------------------------
    # Each of these is something that can break on its own, and each one off is
    # a smaller loss than the app being unusable. Default on, because a switch
    # that defaults to off is a feature nobody ships.
    card_payments = models.BooleanField(
        _("card payments in the app"), default=True,
        help_text=_("Off sends buyers to balance instead. The switch to reach for "
                    "when Stripe, the payment sheet or 3-D Secure is misbehaving."))
    balance_payments = models.BooleanField(_("paying from balance"), default=True)
    balance_topups = models.BooleanField(_("adding balance"), default=True)
    guest_checkout = models.BooleanField(
        _("buying without an account"), default=True,
        help_text=_("Closes guest checkout during an incident. It cannot open it: "
                    "the setting GUEST_CHECKOUT decides whether it is offered at "
                    "all, and that is off."))
    gifting = models.BooleanField(_("gifting an eSIM"), default=True)
    referrals = models.BooleanField(_("referral codes"), default=True)
    coupons = models.BooleanField(_("discount codes"), default=True)
    subscriptions = models.BooleanField(_("subscriptions"), default=True)
    assistant = models.BooleanField(_("the chat assistant"), default=True)
    inbox = models.BooleanField(_("the inbox"), default=True)

    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _("app remote config")
        verbose_name_plural = _("app remote config")

    def __str__(self):
        if self.maintenance:
            return "Remote config — MAINTENANCE"
        off = [name for name, on in self.features().items() if not on]
        return f"Remote config — {', '.join(off) + ' off' if off else 'everything on'}"

    def features(self) -> dict:
        return {
            "card_payments": self.card_payments,
            "balance_payments": self.balance_payments,
            "balance_topups": self.balance_topups,
            "guest_checkout": self.guest_checkout,
            "gifting": self.gifting,
            "referrals": self.referrals,
            "coupons": self.coupons,
            "subscriptions": self.subscriptions,
            "assistant": self.assistant,
            "inbox": self.inbox,
        }

    def payload(self) -> dict:
        """What /api/v1/config/ carries. Shape is fixed: the app in somebody's
        pocket has to keep understanding it."""
        return {
            "maintenance": self.maintenance,
            "maintenance_message": self.maintenance_message if self.maintenance else "",
            "min_supported_version": self.min_supported_version,
            "notice": ({
                "message": self.notice_message,
                "level": self.notice_level,
                "url": self.notice_url,
                "cta": self.notice_cta,
            } if self.notice_message else None),
            "features": self.features(),
        }

    def save(self, *args, **kwargs):
        self.singleton = 1
        super().save(*args, **kwargs)
        cache.delete(CACHE_KEY)

    @classmethod
    def current(cls) -> "RemoteConfig":
        """The live switches.

        Cached for a minute: every app start reads this, and an outage is not
        the moment to add a database round trip to the busiest endpoint. A minute
        is also short enough that flipping a switch during an incident takes
        effect while you are still looking at the screen.

        A cache or database failure must not take the config down with it --
        every caller is asking "what am I allowed to do", and the honest answer
        when we cannot tell is the default one, not an exception.
        """
        try:
            cached = cache.get(CACHE_KEY)
            if cached is not None:
                return cls(**cached)
        except Exception:  # noqa: BLE001
            pass
        try:
            config, _created = cls.objects.get_or_create(singleton=1)
        except Exception:  # noqa: BLE001
            return cls()
        try:
            fields = {f.name: getattr(config, f.name)
                      for f in cls._meta.fields if f.name != "updated_at"}
            cache.set(CACHE_KEY, fields, CACHE_SECONDS)
        except Exception:  # noqa: BLE001
            pass
        return config
