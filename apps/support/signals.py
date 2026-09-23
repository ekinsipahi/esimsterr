"""Chat-log preservation (assistant).

A ``pre_delete`` receiver on :class:`AssistantMessage` copies each message into
the append-only :class:`ArchivedAssistantMessage` table the instant before it is
deleted. A model with connected delete signals is never "fast-deleted", so
Django loads every row and fires this on ALL delete paths — a single message, a
whole conversation, a cascaded user deletion, or account self-deletion
(``accounts.deletion.delete_account``). The archive holds no foreign keys, so
nothing cascades it away: the customer↔operator transcript survives even when the
conversation is deleted.

Never raises — a logging failure must not block or roll back the delete.
"""
import logging

from django.db.models.signals import pre_delete
from django.dispatch import receiver

from .models import ArchivedAssistantMessage, AssistantMessage

log = logging.getLogger(__name__)


@receiver(pre_delete, sender=AssistantMessage, dispatch_uid="archive_assistant_message")
def archive_assistant_message(sender, instance, **kwargs):
    try:
        user_email, user_id = "", ""
        conv = None
        try:
            conv = instance.conversation
        except Exception:  # noqa: BLE001 — conversation may already be gone
            conv = None
        if conv is not None:
            user = getattr(conv, "user", None)
            if user is not None:
                user_email = (getattr(user, "email", "") or "")[:254]
                user_id = str(getattr(user, "pk", "") or "")[:64]
        ArchivedAssistantMessage.objects.create(
            conversation_id=getattr(instance, "conversation_id", None),
            message_id=getattr(instance, "id", None),
            user_id=user_id,
            user_email=user_email,
            role=(getattr(instance, "role", "") or "")[:10],
            content=getattr(instance, "content", "") or "",
            intent=(getattr(instance, "intent", "") or "")[:60],
            message_created_at=getattr(instance, "created_at", None),
        )
    except Exception:  # noqa: BLE001
        log.exception("assistant message archive failed")
