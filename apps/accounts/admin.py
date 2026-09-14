from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin

from .models import AppInstall, User


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    ordering = ("-date_joined",)
    list_display = ("email", "display_name", "yesim_user_id", "is_active", "is_staff", "date_joined")
    list_filter = ("is_active", "is_staff", "marketing_opt_in")
    search_fields = ("email", "display_name", "yesim_user_id", "referral_code")
    readonly_fields = ("id", "date_joined", "last_login", "referral_code", "unsubscribe_token", "signup_ip")
    fieldsets = (
        (None, {"fields": ("id", "email", "password", "display_name")}),
        ("Provider", {"fields": ("yesim_user_id",)}),
        ("Flags", {"fields": ("is_active", "is_staff", "is_superuser", "email_verified", "marketing_opt_in")}),
        ("Referral", {"fields": ("referral_code", "referred_by")}),
        ("Meta", {"fields": ("signup_ip", "date_joined", "last_login", "groups", "user_permissions")}),
    )
    add_fieldsets = (
        (None, {"classes": ("wide",), "fields": ("email", "password1", "password2", "is_staff", "is_superuser")}),
    )
    filter_horizontal = ("groups", "user_permissions")


@admin.register(AppInstall)
class AppInstallAdmin(admin.ModelAdmin):
    """Where support looks up a code a customer read down the phone."""
    list_display = ("support_id", "user", "platform", "app_version",
                    "integrity_verdict", "last_seen")
    list_filter = ("platform", "integrity_verdict", "last_seen")
    search_fields = ("support_id", "user__email")
    readonly_fields = ("support_id", "first_seen", "last_seen",
                       "integrity_verdict", "integrity_checked_at")
    date_hierarchy = "last_seen"

    def has_add_permission(self, request):
        return False
