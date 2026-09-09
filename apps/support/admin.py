from django.contrib import admin

from .models import Reply, Ticket


class ReplyInline(admin.TabularInline):
    model = Reply
    extra = 1
    fields = ("body", "is_staff_reply", "author", "created_at")
    readonly_fields = ("created_at",)


@admin.register(Ticket)
class TicketAdmin(admin.ModelAdmin):
    list_display = ("ref", "created_at", "email", "subject", "category", "status")
    list_filter = ("status", "category", "created_at")
    list_editable = ("status",)
    search_fields = ("ref", "email", "subject", "body", "iccid", "order_ref")
    readonly_fields = ("ref", "created_at", "updated_at")
    inlines = [ReplyInline]
    date_hierarchy = "created_at"
