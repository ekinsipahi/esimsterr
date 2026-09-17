"""The remote-config screen: one row, and it is the one you open during an outage."""
from django.contrib import admin
from django.utils.html import format_html

from .models import RemoteConfig


@admin.register(RemoteConfig)
class RemoteConfigAdmin(admin.ModelAdmin):
    fieldsets = (
        (None, {
            "description": (
                "<b>These take effect within a minute, on every app already "
                "installed.</b> They exist so that a problem in a shipped app can be "
                "contained today rather than after a store review. Turning something "
                "off here costs a feature; leaving it broken costs the sale and the "
                "review."
            ),
            "fields": ("state",),
        }),
        ("Stop everything", {
            "description": "For an outage bad enough that letting people try to buy "
                           "would only take their money into a broken system.",
            "fields": ("maintenance", "maintenance_message"),
        }),
        ("Force an update", {
            "description": "Installs older than this are sent to the store. Raise it "
                           "only for a release that fixes something the old one gets "
                           "wrong with money or data -- it locks people out.",
            "fields": ("min_supported_version",),
        }),
        ("Say something", {
            "description": "A banner at the top of the app. Empty means no banner.",
            "fields": ("notice_message", "notice_level", "notice_cta", "notice_url"),
        }),
        ("Switch a feature off", {
            "description": "Each of these can break on its own, and each one off is a "
                           "smaller loss than the app being unusable.",
            "fields": ("card_payments", "balance_payments", "balance_topups",
                       "guest_checkout", "gifting", "referrals", "coupons",
                       "subscriptions", "assistant", "inbox"),
        }),
    )
    readonly_fields = ("state",)

    @admin.display(description="Right now")
    def state(self, obj):
        if obj.maintenance:
            return format_html('<b style="color:#dc2626">Maintenance mode — the app is '
                               'blocked for everybody.</b>')
        off = [name.replace("_", " ") for name, on in obj.features().items() if not on]
        if off:
            return format_html('<b style="color:#b45309">Off: {}</b>', ", ".join(off))
        return format_html('<b style="color:#16a34a">Everything on, no banner.</b>')

    def has_add_permission(self, request):
        # One row. "Add another" would produce a second set of switches, and
        # half the app would obey the wrong one.
        return not RemoteConfig.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False

    def changelist_view(self, request, extra_context=None):
        """Open the single row rather than a list of one."""
        from django.shortcuts import redirect
        from django.urls import reverse

        config = RemoteConfig.current()
        if config.pk:
            return redirect(reverse("admin:common_remoteconfig_change", args=[config.pk]))
        return super().changelist_view(request, extra_context)
