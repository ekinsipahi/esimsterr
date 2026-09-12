from django.contrib import admin, messages
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _

from .models import Subscription, SubscriptionCycle
from .services import sync_subscription
from .stripe_sub import SubscriptionError


class CycleInline(admin.TabularInline):
    model = SubscriptionCycle
    extra = 0
    fields = ("stripe_invoice_id", "period_start", "period_end", "amount_usd",
              "status", "order", "error")
    readonly_fields = fields
    show_change_link = True
    can_delete = False

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(Subscription)
class SubscriptionAdmin(admin.ModelAdmin):
    list_display = ("created_at", "user_col", "plan_col", "price_col", "status_col",
                    "current_period_end", "renewals_count", "esim_col")
    list_filter = ("status", "cancel_at_period_end", "interval_days", "created_at")
    search_fields = ("user__email", "stripe_subscription_id", "stripe_customer_id",
                     "plan__provider_plan_id", "esim__iccid")
    list_select_related = ("user", "plan", "esim")
    readonly_fields = ("id", "stripe_customer_id", "stripe_subscription_id", "stripe_price_id",
                       "started_at", "canceled_at", "renewals_count", "last_error",
                       "created_at", "updated_at")
    raw_id_fields = ("user", "plan", "esim")
    date_hierarchy = "created_at"
    inlines = [CycleInline]
    actions = ["action_sync"]

    @admin.display(description=_("Customer"), ordering="user__email")
    def user_col(self, obj):
        return obj.user.email

    @admin.display(description=_("Plan"))
    def plan_col(self, obj):
        return obj.title

    @admin.display(description=_("Per cycle"), ordering="price_usd")
    def price_col(self, obj):
        return f"${obj.price_usd} / {obj.interval_days}d"

    @admin.display(description=_("Status"), ordering="status")
    def status_col(self, obj):
        colour = {"active": "#16a34a", "past_due": "#dc2626",
                  "canceled": "#6b7280", "incomplete": "#d97706",
                  "paused": "#6b7280"}.get(obj.status, "#6b7280")
        suffix = _(" (ends at period end)") if obj.cancel_at_period_end else ""
        return format_html('<span style="color:{}">{}{}</span>',
                           colour, obj.get_status_display(), suffix)

    @admin.display(description=_("eSIM"))
    def esim_col(self, obj):
        return obj.esim.iccid if obj.esim_id else "-"

    @admin.action(description=_("Re-sync from Stripe"))
    def action_sync(self, request, queryset):
        ok = err = 0
        for sub in queryset:
            try:
                sync_subscription(sub)
                ok += 1
            except SubscriptionError as e:
                err += 1
                self.message_user(
                    request,
                    _("%(customer)s: %(error)s") % {"customer": sub.user.email, "error": e},
                    level=messages.ERROR,
                )
        self.message_user(request,
                          _("Synced %(ok)s, failed %(failed)s.") % {"ok": ok, "failed": err})


@admin.register(SubscriptionCycle)
class SubscriptionCycleAdmin(admin.ModelAdmin):
    list_display = ("created_at", "subscription", "amount_usd", "status",
                    "period_start", "period_end", "order")
    list_filter = ("status", "created_at")
    search_fields = ("stripe_invoice_id", "subscription__user__email", "order__ref")
    list_select_related = ("subscription", "subscription__user", "order")
    readonly_fields = ("subscription", "stripe_invoice_id", "period_start", "period_end",
                       "amount_usd", "status", "order", "error", "created_at")
    date_hierarchy = "created_at"

    def has_add_permission(self, request):
        return False
