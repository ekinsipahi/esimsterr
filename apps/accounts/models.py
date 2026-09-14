import secrets
import uuid

from django.contrib.auth.models import AbstractBaseUser, PermissionsMixin
from django.conf import settings
from django.db import models
from django.utils import timezone

from .managers import UserManager


class User(AbstractBaseUser, PermissionsMixin):
    """Email-based user. Minimal data: email + optional display name."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    email = models.EmailField(unique=True)
    display_name = models.CharField(max_length=80, blank=True)

    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)
    # Proved to belong to whoever registered. Google sign-in sets it straight
    # away -- Google has already done the proving, and asking someone to confirm
    # an address they just authenticated with is friction that buys nothing.
    # Email registration now sends a link and refuses sign-in until it is used;
    # the field existed before that and was simply never enforced.
    email_verified = models.BooleanField(default=False)

    # Provider-side account (Yesim /new_user). Created lazily on first purchase.
    yesim_user_id = models.CharField(max_length=32, blank=True, db_index=True)
    # Where saved cards live. Stripe holds the card; we hold this id and nothing
    # that could be used to charge anyone anywhere else.
    stripe_customer_id = models.CharField(max_length=64, blank=True, db_index=True)

    signup_ip = models.GenericIPAddressField(null=True, blank=True)
    marketing_opt_in = models.BooleanField(default=True)
    unsubscribe_token = models.CharField(max_length=48, blank=True, db_index=True)
    referral_code = models.CharField(max_length=16, unique=True, blank=True, null=True)
    referred_by = models.ForeignKey(
        "self", null=True, blank=True, on_delete=models.SET_NULL, related_name="referrals"
    )
    email_verified_at = models.DateTimeField(null=True, blank=True)

    date_joined = models.DateTimeField(default=timezone.now)

    objects = UserManager()

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = []

    class Meta:
        db_table = "users"
        ordering = ["-date_joined"]

    def __str__(self):
        return self.email

    def save(self, *args, **kwargs):
        if not self.unsubscribe_token:
            self.unsubscribe_token = secrets.token_urlsafe(24)
        if not self.referral_code:
            alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
            while True:
                code = "".join(secrets.choice(alphabet) for _ in range(8))
                if not User.objects.filter(referral_code=code).exists():
                    self.referral_code = code
                    break
        super().save(*args, **kwargs)

    @property
    def short_name(self):
        return self.display_name or self.email.split("@")[0]


class AppInstall(models.Model):
    """One installation of the mobile app.

    The support id is generated on the device and sent as a header. It is a
    random label for an installation -- not an advertising id, not a hardware
    serial, nothing derivable from the person -- and it exists so that "I bought
    something on my phone, I think" becomes a database lookup while the customer
    is still on the line.

    A row can outlive an account: a guest buys, contacts support, and only signs
    up later. Linking the user when one appears is what joins those together.
    """

    support_id = models.CharField(max_length=24, unique=True, db_index=True)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True,
                             on_delete=models.SET_NULL, related_name="installs")
    platform = models.CharField(max_length=12, default="android")
    app_version = models.CharField(max_length=20, blank=True)
    # Play Integrity outcome, in words, so a support answer does not require
    # decoding a verdict blob. Empty means never checked.
    # A device that buys without an account still gets its card back next time,
    # which is the only reason saving one is worth anything to a guest.
    stripe_customer_id = models.CharField(max_length=64, blank=True, db_index=True)

    integrity_verdict = models.CharField(max_length=120, blank=True)
    integrity_checked_at = models.DateTimeField(null=True, blank=True)

    first_seen = models.DateTimeField(auto_now_add=True)
    last_seen = models.DateTimeField(auto_now=True, db_index=True)

    @property
    def is_attested(self) -> bool:
        return self.integrity_verdict == "verified"

    class Meta:
        verbose_name = "app install"
        verbose_name_plural = "app installs"
        ordering = ("-last_seen",)

    def __str__(self):
        return f"{self.support_id} ({self.platform})"
