from django.contrib import admin

from .models import LegalAcceptance


@admin.register(LegalAcceptance)
class LegalAcceptanceAdmin(admin.ModelAdmin):
    """Read-only on purpose.

    The value of this table is that nobody edited it. An admin who can change a
    row can change what a customer is recorded as having agreed to, which is
    exactly the claim the table exists to support.
    """
    list_display = ("created_at", "email", "document", "version", "context", "surface", "order_ref")
    list_filter = ("document", "context", "surface", "created_at")
    search_fields = ("email", "order_ref", "version", "ip")
    date_hierarchy = "created_at"
    ordering = ("-created_at",)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
