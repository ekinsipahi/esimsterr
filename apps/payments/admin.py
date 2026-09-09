from django.contrib import admin, messages

from .models import Payment
from .services import settle_payment


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = ("created_at", "order_ref", "provider", "amount_usd",
                    "paid_amount_usd", "status", "settled")
    list_filter = ("provider", "status", "settled", "created_at")
    search_fields = ("id", "provider_payment_id", "provider_session_id",
                     "order__ref", "order__email", "user__email")
    readonly_fields = ("id", "order", "user", "provider", "provider_payment_id",
                       "provider_session_id", "amount_usd", "checkout_url", "raw",
                       "created_at", "updated_at")
    list_select_related = ("order", "user")
    actions = ["action_settle"]
    date_hierarchy = "created_at"

    @admin.display(description="Order", ordering="order__ref")
    def order_ref(self, obj):
        return obj.order.ref

    @admin.action(description="Force settle (money confirmed off-platform)")
    def action_settle(self, request, queryset):
        n = 0
        for payment in queryset.filter(settled=False):
            try:
                settle_payment(payment.pk, paid_amount_usd=payment.amount_usd)
                n += 1
            except Exception as e:  # noqa: BLE001
                self.message_user(request, f"{payment.id}: {e}", level=messages.ERROR)
        self.message_user(request, f"Settled {n} payment(s).")
