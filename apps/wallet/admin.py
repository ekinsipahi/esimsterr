from django.contrib import admin

from .models import BalanceTopUp, Wallet, WalletTransaction


class TransactionInline(admin.TabularInline):
    model = WalletTransaction
    extra = 0
    can_delete = False
    readonly_fields = ("kind", "amount_usd", "balance_after_usd", "description",
                       "order", "balance_topup", "created_at")
    fields = readonly_fields
    ordering = ("-created_at",)

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(Wallet)
class WalletAdmin(admin.ModelAdmin):
    list_display = ("user", "balance_usd", "topped_up_usd", "spent_usd", "updated_at")
    search_fields = ("user__email",)
    readonly_fields = ("balance_usd", "topped_up_usd", "spent_usd", "created_at", "updated_at")
    inlines = [TransactionInline]

    def has_add_permission(self, request):
        return False


@admin.register(WalletTransaction)
class WalletTransactionAdmin(admin.ModelAdmin):
    """Read-only: the ledger is the audit trail, and an editable audit trail is
    not one. Corrections are made by adding an ADJUST row, never by editing."""
    list_display = ("created_at", "wallet", "kind", "amount_usd", "balance_after_usd", "description")
    list_filter = ("kind", "created_at")
    search_fields = ("wallet__user__email", "description", "order__ref")
    date_hierarchy = "created_at"

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(BalanceTopUp)
class BalanceTopUpAdmin(admin.ModelAdmin):
    list_display = ("ref", "user", "amount_usd", "bonus_usd", "credited_usd",
                    "status", "source", "created_at")
    list_filter = ("status", "source", "created_at")
    search_fields = ("ref", "user__email")
    date_hierarchy = "created_at"
    readonly_fields = ("ref", "credited_usd", "credited_at", "created_at", "ip")
    actions = ("credit_now",)

    @admin.action(description="Credit these top-ups to the wallet (idempotent)")
    def credit_now(self, request, queryset):
        from .services import credit_topup

        done = 0
        for topup in queryset:
            if topup.status in (BalanceTopUp.Status.PAID, BalanceTopUp.Status.CREDITED):
                credit_topup(topup)
                done += 1
        self.message_user(request, f"Credited {done} top-up(s).")
