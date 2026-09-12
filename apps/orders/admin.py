from django.contrib import admin, messages
from django.utils.html import format_html

from .models import Esim, Order, WebhookEvent
from .services import fulfill_order, sync_esim


class EsimInline(admin.TabularInline):
    model = Esim
    fk_name = "order"
    extra = 0
    fields = ("iccid", "status_qr", "plan_title", "plan_expires_at", "data_used_mb")
    readonly_fields = fields
    show_change_link = True
    can_delete = False

    def has_add_permission(self, request, obj=None):
        return False


class GuestFilter(admin.SimpleListFilter):
    """Guest orders are the ones with no account behind them, and the ones most
    worth eyeballing: they are where card fraud and coupon abuse show up."""

    title = "buyer"
    parameter_name = "buyer"

    def lookups(self, request, model_admin):
        return (("guest", "Guest (no account)"), ("account", "Signed-in account"))

    def queryset(self, request, queryset):
        if self.value() == "guest":
            return queryset.filter(user__isnull=True)
        if self.value() == "account":
            return queryset.filter(user__isnull=False)
        return queryset


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = ("ref", "created_at", "buyer_col", "plan_title", "amount_col",
                    "margin_col", "status", "kind", "ip", "attempts_col")
    list_filter = ("status", "kind", GuestFilter, "created_at", "coupon")
    search_fields = ("ref", "email", "plan_title", "user__email", "esims__iccid",
                     "ip", "coupon_code")
    readonly_fields = ("id", "ref", "created_at", "paid_at", "completed_at", "margin_col",
                       "plan_provider_id", "cost_amount", "cost_currency",
                       "ip", "user_agent", "accept_language", "referrer",
                       "subtotal_usd", "discount_usd", "coupon_code",
                       "fulfillment_attempts", "fulfillment_error")
    list_select_related = ("plan", "user")
    inlines = [EsimInline]
    actions = ["action_fulfill", "action_mark_paid"]
    date_hierarchy = "created_at"

    @admin.display(description="Buyer", ordering="email")
    def buyer_col(self, obj):
        if obj.user_id:
            return format_html('{} <span style="color:#888">(account)</span>', obj.email)
        return format_html('{} <span style="color:#b45309">(guest)</span>', obj.email)

    @admin.display(description="Amount", ordering="amount_usd")
    def amount_col(self, obj):
        if obj.discount_usd and obj.discount_usd > 0:
            return format_html('<b>${}</b> <span style="color:#16a34a">-${} {}</span>',
                               f"{obj.amount_usd}", f"{obj.discount_usd}", obj.coupon_code)
        return f"${obj.amount_usd}"

    @admin.display(description="Margin")
    def margin_col(self, obj):
        m = obj.margin_usd
        return format_html('<span style="color:{}">${}</span>',
                           "#16a34a" if m > 0 else "#dc2626", f"{m:.2f}")

    @admin.display(description="Tries")
    def attempts_col(self, obj):
        if obj.fulfillment_error:
            return format_html('<span style="color:#dc2626" title="{}">{} ⚠</span>',
                               obj.fulfillment_error[:200], obj.fulfillment_attempts)
        return obj.fulfillment_attempts

    @admin.action(description="Provision eSIM now (retry fulfilment)")
    def action_fulfill(self, request, queryset):
        ok = err = 0
        for order in queryset:
            try:
                fulfill_order(order.pk)
                ok += 1
            except Exception as e:  # noqa: BLE001
                err += 1
                self.message_user(request, f"{order.ref}: {e}", level=messages.ERROR)
        self.message_user(request, f"Provisioned {ok}, failed {err}.")

    @admin.action(description="Mark as paid (manual settlement)")
    def action_mark_paid(self, request, queryset):
        n = 0
        for order in queryset.filter(status=Order.Status.PENDING):
            order.mark_paid()
            n += 1
        self.message_user(request, f"{n} order(s) marked paid. Run 'Provision eSIM now' next.")


@admin.register(Esim)
class EsimAdmin(admin.ModelAdmin):
    list_display = ("iccid", "email", "plan_title", "status_qr", "usage_col",
                    "plan_expires_at", "last_synced_at")
    list_filter = ("status_qr", "is_unlimited", "is_deleted", "provider")
    search_fields = ("iccid", "email", "user__email", "imsi", "msisdn", "label")
    readonly_fields = ("id", "iccid", "lpa_code", "ios_tap_link", "esim_passport_url",
                       "provider_esim_id", "provider_user_id", "imsi", "msisdn",
                       "network_info", "created_at", "updated_at", "last_synced_at")
    list_select_related = ("user", "order")
    actions = ["action_sync"]

    @admin.display(description="Usage")
    def usage_col(self, obj):
        if obj.is_unlimited:
            return f"{obj.data_used_mb or 0} MB (unlimited)"
        if obj.data_package_mb:
            return f"{obj.data_used_mb or 0} / {obj.data_package_mb} MB ({obj.data_used_pct}%)"
        return "—"

    @admin.action(description="Refresh usage from provider")
    def action_sync(self, request, queryset):
        ok = err = 0
        for esim in queryset:
            try:
                sync_esim(esim)
                ok += 1
            except Exception as e:  # noqa: BLE001
                err += 1
                self.message_user(request, f"{esim.iccid}: {e}", level=messages.ERROR)
        self.message_user(request, f"Synced {ok}, failed {err}.")


@admin.register(WebhookEvent)
class WebhookEventAdmin(admin.ModelAdmin):
    list_display = ("created_at", "source", "event_type", "iccid", "processed")
    list_filter = ("source", "event_type", "processed")
    search_fields = ("iccid", "payload")
    readonly_fields = ("source", "event_type", "iccid", "payload", "processed", "error", "created_at")


class GuestOrder(Order):
    """Admin-only proxy: the guest-checkout audit trail in one screen.

    The owner asked to be able to see who bought what without an account, so this
    view leads with the request fingerprint (IP, user agent, referrer) rather
    than with the product.
    """

    class Meta:
        proxy = True
        verbose_name = "Guest order (audit)"
        verbose_name_plural = "Guest orders (audit)"


@admin.register(GuestOrder)
class GuestOrderAdmin(admin.ModelAdmin):
    list_display = ("created_at", "ip", "email", "amount_col", "status",
                    "plan_title", "coupon_code", "ua_col")
    list_filter = ("status", "created_at")
    search_fields = ("ip", "email", "ref", "user_agent", "referrer", "coupon_code")
    date_hierarchy = "created_at"
    readonly_fields = [f.name for f in Order._meta.fields]

    def get_queryset(self, request):
        return super().get_queryset(request).filter(user__isnull=True)

    def has_add_permission(self, request):
        return False

    @admin.display(description="Paid", ordering="amount_usd")
    def amount_col(self, obj):
        return f"${obj.amount_usd}"

    @admin.display(description="Device / referrer")
    def ua_col(self, obj):
        return format_html('<span title="{}">{}</span>',
                           obj.referrer or "no referrer", (obj.user_agent or "-")[:60])
