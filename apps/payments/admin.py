from django.contrib import admin, messages

from .models import Payment
from .services import settle_payment


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = ("created_at", "bought", "provider", "amount_usd",
                    "paid_amount_usd", "status", "settled")
    list_filter = ("provider", "status", "settled", "created_at")
    search_fields = ("id", "provider_payment_id", "provider_session_id",
                     "order__ref", "order__email", "balance_topup__ref",
                     "balance_topup__user__email", "user__email")
    readonly_fields = ("id", "order", "balance_topup", "user", "provider",
                       "provider_payment_id", "provider_session_id", "amount_usd",
                       "checkout_url", "raw", "created_at", "updated_at")
    list_select_related = ("order", "balance_topup", "user")
    actions = ["action_settle"]
    date_hierarchy = "created_at"

    @admin.display(description="Bought")
    def bought(self, obj):
        """An order or store credit -- a payment is for exactly one of them.

        This column used to read obj.order.ref unconditionally, so the whole
        changelist raised AttributeError the moment anybody paid for balance, and
        the page that lists payments was the page you could not open.
        """
        if obj.order_id:
            return obj.order.ref
        if obj.balance_topup_id:
            return f"{obj.balance_topup.ref} (balance)"
        return "—"

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
