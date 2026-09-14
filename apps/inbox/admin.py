from django.contrib import admin
from django.utils import timezone

from .models import InboxMessage, InboxRead


@admin.register(InboxMessage)
class InboxMessageAdmin(admin.ModelAdmin):
    list_display = ("title", "kind", "audience", "is_published", "publish_at",
                    "expires_at", "read_count")
    list_filter = ("kind", "audience", "is_published", "publish_at")
    search_fields = ("title", "body", "coupon_code")
    date_hierarchy = "publish_at"
    actions = ("publish_now", "unpublish")
    fieldsets = (
        (None, {"fields": ("title", "body", "kind", "audience")}),
        ("Call to action", {"fields": ("cta_label", "cta_url", "coupon_code")}),
        ("Scheduling", {"fields": ("is_published", "publish_at", "expires_at")}),
    )

    @admin.display(description="Read by")
    def read_count(self, obj):
        return obj.reads.count()

    @admin.action(description="Publish now")
    def publish_now(self, request, queryset):
        n = queryset.update(is_published=True, publish_at=timezone.now())
        self.message_user(request, f"Published {n} message(s).")

    @admin.action(description="Unpublish")
    def unpublish(self, request, queryset):
        n = queryset.update(is_published=False)
        self.message_user(request, f"Unpublished {n} message(s).")


@admin.register(InboxRead)
class InboxReadAdmin(admin.ModelAdmin):
    list_display = ("user", "message", "read_at")
    list_filter = ("read_at",)
    search_fields = ("user__email", "message__title")

    def has_add_permission(self, request):
        return False
