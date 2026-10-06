from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.urls import reverse
from django.utils.html import format_html, format_html_join
from django.utils.safestring import mark_safe

from .models import AppInstall, LoginEvent, User

# How many sign-ins to show inline on an account page. Enough to see a pattern
# (one person, one city, one browser) without turning the page into a log file;
# the "all sign-ins" link goes to the rest.
RECENT_SIGNINS = 12


def _ip_search_link(ip, label=None):
    """Link an address to every sign-in that came from it.

    The question that actually gets asked about an address is never "what is
    it", it is "who else came from here" -- six accounts sharing one address
    within an hour is a ring, and the same six spread over a month is a family
    or an office. Making the address clickable is the whole feature.
    """
    if not ip:
        return "—"
    url = reverse("admin:accounts_loginevent_changelist") + f"?ip={ip}"
    return format_html('<a href="{}">{}</a>', url, label or ip)


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    ordering = ("-date_joined",)
    list_display = ("email", "display_name", "yesim_user_id", "signup_ip_link",
                    "last_login_ip_link", "is_active", "is_staff", "date_joined")
    list_filter = ("is_active", "is_staff", "marketing_opt_in", "is_test")
    # An address is searchable because a fraud question usually arrives as one:
    # support or Stripe hands over an IP, not an email.
    search_fields = ("email", "display_name", "yesim_user_id", "referral_code",
                     "signup_ip", "last_login_ip")
    readonly_fields = ("id", "date_joined", "last_login", "referral_code",
                       "unsubscribe_token", "signup_ip", "last_login_ip",
                       "recent_signins", "card_block_status")
    fieldsets = (
        (None, {"fields": ("id", "email", "password", "display_name")}),
        ("Provider", {"fields": ("yesim_user_id",)}),
        ("Flags", {"fields": ("is_active", "is_staff", "is_superuser", "email_verified", "marketing_opt_in")}),
        ("Referral", {"fields": ("referral_code", "referred_by")}),
        ("Where from", {"fields": ("signup_ip", "last_login_ip", "recent_signins")}),
        ("Card payments", {"fields": ("card_block_status",)}),
        ("Meta", {"fields": ("date_joined", "last_login", "groups", "user_permissions")}),
    )
    add_fieldsets = (
        (None, {"classes": ("wide",), "fields": ("email", "password1", "password2", "is_staff", "is_superuser")}),
    )
    filter_horizontal = ("groups", "user_permissions")

    @admin.display(description="Signed up from", ordering="signup_ip")
    def signup_ip_link(self, obj):
        return _ip_search_link(obj.signup_ip)

    @admin.display(description="Last seen from", ordering="last_login_ip")
    def last_login_ip_link(self, obj):
        return _ip_search_link(obj.last_login_ip)

    @admin.display(description="Recent sign-ins")
    def recent_signins(self, obj):
        if not obj.pk:
            return "—"
        rows = obj.login_events.all()[:RECENT_SIGNINS]
        if not rows:
            return mark_safe(
                "<em>Nothing recorded. Accounts that predate the sign-in log, "
                "or app accounts from before it covered them, show up empty "
                "here until their next sign-in.</em>"
            )
        body = format_html_join(
            "", "<tr><td>{}</td><td>{}</td><td>{}</td><td>{}</td>"
                "<td style=\"max-width:28em;overflow:hidden\">{}</td></tr>",
            (
                (r.created_at.strftime("%Y-%m-%d %H:%M"), r.get_event_display(),
                 r.get_method_display(), _ip_search_link(r.ip), r.user_agent or "—")
                for r in rows
            ),
        )
        all_url = reverse("admin:accounts_loginevent_changelist") + f"?user__id__exact={obj.pk}"
        return format_html(
            '<table><thead><tr><th>When</th><th>What</th><th>How</th>'
            '<th>From</th><th>Device</th></tr></thead><tbody>{}</tbody></table>'
            '<p><a href="{}">All sign-ins for this account →</a></p>',
            body, all_url,
        )


    @admin.display(description="Card status")
    def card_block_status(self, obj):
        """Whether this account is on the fraud blocklist, said in words.

        The blocklist itself is keyed by account id, so its own screen shows a
        UUID where a person should be. Asking the question from the side that
        knows who the account belongs to is the way round that answers "is this
        the one who was banned" without anybody copying identifiers between two
        tabs.
        """
        if not obj.pk:
            return "—"
        from payguard import is_permanently_blocked
        from payguard.models import CardCooldown

        blocked = is_permanently_blocked(user=obj, email=obj.email)
        rows = CardCooldown.objects.filter(
            permanent=True,
            kind__in=[CardCooldown.Kind.ACCOUNT, CardCooldown.Kind.EMAIL],
            key__in=[str(obj.pk), (obj.email or "").lower()],
        )
        url = reverse("admin:payguard_cardcooldown_changelist") + "?permanent__exact=1"
        if not blocked:
            return format_html(
                'Card payments allowed. <a href="{}">Blocklist →</a>', url)
        why = "; ".join(r.reason for r in rows if r.reason) or "no reason recorded"
        return format_html(
            '<strong style="color:#b00">Blocked from card payments.</strong> {}'
            '<br><a href="{}">Lift it on the blocklist screen →</a>', why, url)


@admin.register(LoginEvent)
class LoginEventAdmin(admin.ModelAdmin):
    """Where accounts are signed up and signed in from.

    Read-only on purpose. It is the thing a chargeback reply and a fraud
    question both point at, and evidence that staff can edit is not evidence.
    """

    list_display = ("created_at", "email", "event", "method", "surface",
                    "ip_link", "short_agent")
    list_filter = ("event", "method", "surface", "created_at")
    search_fields = ("user__email", "ip", "user_agent")
    date_hierarchy = "created_at"
    list_select_related = ("user",)

    @admin.display(description="Account", ordering="user__email")
    def email(self, obj):
        url = reverse("admin:accounts_user_change", args=[obj.user_id])
        return format_html('<a href="{}">{}</a>', url, obj.user.email)

    @admin.display(description="From", ordering="ip")
    def ip_link(self, obj):
        return _ip_search_link(obj.ip)

    @admin.display(description="Device")
    def short_agent(self, obj):
        return (obj.user_agent[:70] + "…") if len(obj.user_agent) > 70 else (obj.user_agent or "—")

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


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
