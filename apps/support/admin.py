"""Operator console.

The admin is where support is actually done: a staff reply is written in the
ticket inline and the customer email goes out from `save_formset`, so there is
no second screen to forget. The same hook powers operator takeover in chat --
writing a message as the team silences the AI for that conversation.
"""
from __future__ import annotations

from django import forms
from django.conf import settings
from django.contrib import admin, messages
from django.db.models import F
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _
from django.utils.translation import ngettext

from apps.accounts.emails import send_email_bg

from .assistant import INTENT_FLAGS
from .models import AssistantConversation, AssistantMessage, Ticket, TicketMessage


class TicketMessageInlineForm(forms.ModelForm):
    class Meta:
        model = TicketMessage
        fields = ("role", "body")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Anything typed here by an operator is a staff reply unless they say
        # otherwise, so the customer email fires without an extra click.
        if not self.instance.pk:
            self.fields["role"].initial = TicketMessage.Role.STAFF


class TicketMessageInline(admin.TabularInline):
    model = TicketMessage
    form = TicketMessageInlineForm
    extra = 1
    fields = ("role", "body", "created_at")
    readonly_fields = ("created_at",)


@admin.register(Ticket)
class TicketAdmin(admin.ModelAdmin):
    list_display = ("ref", "created_at", "email", "who", "subject", "category", "status")
    list_filter = ("status", "category", "created_at")
    list_editable = ("status",)
    search_fields = ("ref", "email", "subject", "messages__body", "iccid", "order_ref")
    readonly_fields = ("ref", "created_at", "updated_at", "ip", "user_agent", "customer_link")
    inlines = [TicketMessageInline]
    date_hierarchy = "created_at"
    list_select_related = ("user",)
    fieldsets = (
        (None, {"fields": ("ref", "status", "category", "subject")}),
        (_("Customer"), {"fields": ("user", "email", "order_ref", "iccid", "customer_link")}),
        (_("Trace"), {"fields": ("ip", "user_agent", "created_at", "updated_at"),
                      "classes": ("collapse",)}),
    )

    @admin.display(description=_("account"), boolean=True)
    def who(self, obj):
        return bool(obj.user_id)

    @admin.display(description=_("customer link"))
    def customer_link(self, obj):
        if not obj.pk:
            return "-"
        url = f"{settings.SITE_URL}{obj.guest_url}"
        return format_html('<a href="{}" target="_blank" rel="noopener">{}</a>', url, url)

    def save_formset(self, request, form, formset, change):
        if formset.model is not TicketMessage:
            return super().save_formset(request, form, formset, change)

        instances = formset.save(commit=False)
        for obj in formset.deleted_objects:
            obj.delete()
        new_staff = []
        for obj in instances:
            # _state.adding, not `pk is None`: message ids can be model-level
            # defaults, so a brand new row already carries a primary key here.
            is_new = obj._state.adding
            obj.save()
            if is_new and obj.role == TicketMessage.Role.STAFF:
                new_staff.append(obj)
        formset.save_m2m()

        if not new_staff:
            return
        ticket = form.instance
        # Only flip to "answered" if the operator did not set a status by hand
        # in the same save (closing a thread with a final word is common, and so
        # is leaving it open on purpose while the fix is still in progress).
        if "status" not in form.changed_data and ticket.status != Ticket.Status.ANSWERED:
            ticket.status = Ticket.Status.ANSWERED
            ticket.save(update_fields=["status", "updated_at"])
        body = "\n\n".join(m.body for m in new_staff)
        send_email_bg(
            ticket.email, f"Re: {ticket.subject} ({ticket.ref})", "ticket_reply",
            {"ticket": ticket, "body": body,
             "ticket_url": f"{settings.SITE_URL}{ticket.guest_url}"},
            reply_to=getattr(settings, "SUPPORT_FORWARD_EMAIL", "") or settings.SUPPORT_EMAIL,
        )
        messages.info(request, _("Reply emailed to %(email)s.") % {"email": ticket.email})


class IntentFlagFilter(admin.SimpleListFilter):
    """intent_flags is a comma string, so filtering is a substring match. Good
    enough for a handful of fixed flag names and it needs no extra table."""

    title = _("intent")
    parameter_name = "flag"

    def lookups(self, request, model_admin):
        return [(f, f) for f in INTENT_FLAGS]

    def queryset(self, request, queryset):
        value = self.value()
        return queryset.filter(intent_flags__contains=value) if value else queryset


class AssistantMessageInlineForm(forms.ModelForm):
    class Meta:
        model = AssistantMessage
        fields = ("role", "content")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if not self.instance.pk:
            self.fields["role"].initial = AssistantMessage.Role.OWNER


class AssistantMessageInline(admin.TabularInline):
    model = AssistantMessage
    form = AssistantMessageInlineForm
    extra = 1
    fields = ("role", "content", "intent", "created_at")
    readonly_fields = ("intent", "created_at")


@admin.register(AssistantConversation)
class AssistantConversationAdmin(admin.ModelAdmin):
    list_display = ("short_id", "user", "status", "intent_flags", "owner_joined",
                    "user_unread", "updated_at")
    list_filter = ("status", "owner_joined", IntentFlagFilter, "updated_at")
    search_fields = ("user__email", "intent_flags", "messages__content")
    readonly_fields = ("id", "ip", "user_agent", "escalated_at", "created_at",
                       "updated_at", "intent_flags")
    inlines = [AssistantMessageInline]
    list_select_related = ("user",)
    actions = ("toggle_owner_joined", "close_conversations")

    @admin.display(description=_("chat"))
    def short_id(self, obj):
        return str(obj.id)[:8]

    @admin.action(description=_("Toggle operator takeover (silences the AI)"))
    def toggle_owner_joined(self, request, queryset):
        joined = handed_back = 0
        for conv in queryset:
            conv.owner_joined = not conv.owner_joined
            conv.save(update_fields=["owner_joined", "updated_at"])
            if conv.owner_joined:
                joined += 1
            else:
                handed_back += 1
        self.message_user(
            request,
            ngettext("%(n)d conversation taken over.", "%(n)d conversations taken over.", joined)
            % {"n": joined} + " " +
            ngettext("%(n)d handed back to the assistant.",
                     "%(n)d handed back to the assistant.", handed_back) % {"n": handed_back},
        )

    @admin.action(description=_("Close selected conversations"))
    def close_conversations(self, request, queryset):
        n = queryset.update(status=AssistantConversation.Status.CLOSED)
        self.message_user(request, _("%(n)d closed.") % {"n": n})

    def save_formset(self, request, form, formset, change):
        if formset.model is not AssistantMessage:
            return super().save_formset(request, form, formset, change)

        instances = formset.save(commit=False)
        for obj in formset.deleted_objects:
            obj.delete()
        new_owner = 0
        for obj in instances:
            is_new = obj._state.adding  # UUID pk is set before save; see above
            obj.save()
            if is_new and obj.role == AssistantMessage.Role.OWNER:
                new_owner += 1
        formset.save_m2m()

        if new_owner:
            conv = form.instance
            # A human wrote: take the conversation off the AI and raise the
            # widget badge so the customer notices the reply.
            conv.owner_joined = True
            # F(), not read-modify-write: the customer's widget clears this
            # column from another request, and a reply counted against a stale
            # number is a reply the customer is never told about.
            conv.user_unread = F("user_unread") + new_owner
            conv.save(update_fields=["owner_joined", "user_unread", "updated_at"])
            conv.refresh_from_db(fields=["user_unread"])

