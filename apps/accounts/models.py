import secrets
import uuid

from django.contrib.auth.models import AbstractBaseUser, PermissionsMixin
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
    email_verified = models.BooleanField(default=False)

    # Provider-side account (Yesim /new_user). Created lazily on first purchase.
    yesim_user_id = models.CharField(max_length=32, blank=True, db_index=True)

    signup_ip = models.GenericIPAddressField(null=True, blank=True)
    marketing_opt_in = models.BooleanField(default=True)
    unsubscribe_token = models.CharField(max_length=48, blank=True, db_index=True)
    referral_code = models.CharField(max_length=16, unique=True, blank=True, null=True)
    referred_by = models.ForeignKey(
        "self", null=True, blank=True, on_delete=models.SET_NULL, related_name="referrals"
    )
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
