"""The live operator inbox: /admin/assistant/.

The Django admin change form can already deliver an operator reply, but it is
the wrong shape for this job. It answers one conversation at a time, shows
nothing until you reload, and gives no sign that somebody is sitting in the chat
waiting. This is the two-pane version: the queue on the left, the thread on the
right, a chime and a red count when a customer starts waiting, and one click to
take the conversation off the AI.

POLLING BUDGET
--------------
A left-open inbox polls for hours, so every request here is written to be cheap
when nothing has happened -- which is almost always.

* Both endpoints take a cursor (`v`) and answer `{"unchanged": true}` when it
  still matches. That path is one aggregate over an indexed column and no
  serialisation at all.
* The list never walks messages per conversation. The last line comes from a
  Subquery, so the cost is one query whatever the queue length.
* The thread takes `after` and returns only messages newer than that, so an open
  conversation re-sends nothing it has already sent.

The client half of the bargain -- stop polling on a hidden tab, back off on
errors, never let two requests overlap -- is in the template.
"""
from __future__ import annotations

import json

from django.contrib.admin.views.decorators import staff_member_required
from django.db.models import Count, Max, OuterRef, Subquery
from django.http import JsonResponse
from django.shortcuts import render
from django.utils.dateparse import parse_datetime
from django.views.decorators.http import require_GET, require_POST

from .models import AssistantConversation, AssistantMessage

_C = AssistantConversation
_M = AssistantMessage

# How many conversations the queue shows. Beyond this the operator is not
# reading a queue, they are reading history -- which the Django admin does
# better, with filters and search.
QUEUE_LIMIT = 100
# A thread this long is a support failure of its own; the cap exists so one
# pathological conversation cannot make every poll expensive.
THREAD_LIMIT = 300

# Said in the customer's chat when the operator hands the conversation back.
# Deliberately not an apology: the AI is genuinely able to carry on from here.
RESUME_MESSAGE = (
    "A member of the team has stepped out of the chat — I am back and happy to keep "
    "helping. What else can I do for you?"
)


def _message_json(message: _M) -> dict:
    return {
        "id": str(message.id),
        "role": message.role,
        "content": message.content,
        "created_at": message.created_at.isoformat(),
    }


def _thread_cursor(conv: _C, last_message_at) -> str:
    """Everything the right-hand pane can show, folded into one short string.

    Message arrival is the usual reason to redraw, but not the only one: the
    operator in another tab may have taken the conversation over or closed it,
    and the pane has to notice that too.
    """
    stamp = (last_message_at or conv.updated_at).timestamp()
    return f"{stamp:.6f}:{conv.status}:{int(conv.owner_joined)}"


@staff_member_required
def assistant_inbox(request):
    return render(request, "admin/assistant_inbox.html", {"title": "Assistant inbox"})


@staff_member_required
@require_GET
def assistant_inbox_data(request):
    """`?conv=<id>` for one thread, otherwise the queue. `v` short-circuits both."""
    conv_id = (request.GET.get("conv") or "").strip()
    client_cursor = request.GET.get("v") or ""

    if conv_id:
        conv = _C.objects.filter(pk=conv_id).select_related("user").first()
        if conv is None:
            return JsonResponse({"error": "not_found"}, status=404)

        last_at = conv.messages.aggregate(t=Max("created_at"))["t"]
        cursor = _thread_cursor(conv, last_at)
        if client_cursor and client_cursor == cursor:
            return JsonResponse({"unchanged": True, "v": cursor})

        messages = conv.messages.all()
        # `after` is the timestamp of the newest message the operator's screen
        # already holds. Sending what they have again would be free to compute
        # and wasteful to transfer, and would make the pane flicker.
        after = parse_datetime(request.GET.get("after") or "")
        if after is not None:
            messages = messages.filter(created_at__gt=after)
            incremental = True
        else:
            incremental = False
        rows = [_message_json(m) for m in messages[:THREAD_LIMIT]]

        return JsonResponse({
            "v": cursor,
            "id": str(conv.id),
            "user": conv.user.email,
            "user_id": str(conv.user_id),
            "status": conv.status,
            "flags": conv.flag_list,
            "owner_joined": conv.owner_joined,
            "started_at": conv.created_at.isoformat(),
            "incremental": incremental,
            "messages": rows,
        })

    live = _C.objects.exclude(status=_C.Status.CLOSED)
    summary = live.aggregate(n=Count("pk"), t=Max("updated_at"))
    stamp = summary["t"].timestamp() if summary["t"] else 0
    cursor = f"{summary['n']}:{stamp:.6f}"
    if client_cursor and client_cursor == cursor:
        return JsonResponse({"unchanged": True, "v": cursor})

    newest = _M.objects.filter(conversation=OuterRef("pk")).order_by("-created_at")
    queue = (
        live.select_related("user")
        .annotate(
            last_body=Subquery(newest.values("content")[:1]),
            last_role=Subquery(newest.values("role")[:1]),
        )
        .order_by("-updated_at")[:QUEUE_LIMIT]
    )

    conversations = []
    for conv in queue:
        # The customer wrote last, so they are sitting there looking at the
        # widget. This is the only thing on the screen that makes a noise.
        waiting = conv.last_role == _M.Role.USER
        conversations.append({
            "id": str(conv.id),
            "user": conv.user.email,
            "status": conv.status,
            "flags": conv.flag_list,
            "owner_joined": conv.owner_joined,
            "last": (conv.last_body or "")[:120],
            "last_role": conv.last_role or "",
            "waiting": waiting,
            "updated_at": conv.updated_at.isoformat(),
        })

    return JsonResponse({
        "v": cursor,
        "conversations": conversations,
        "waiting": sum(1 for c in conversations if c["waiting"]),
    })


@staff_member_required
@require_POST
def assistant_reply(request):
    """`{conv, message}` to answer as a human, `{conv, action}` to take/hand back/close."""
    try:
        data = json.loads(request.body.decode() or "{}")
        if not isinstance(data, dict):
            raise ValueError
    except (ValueError, UnicodeDecodeError):
        return JsonResponse({"error": "bad_json"}, status=400)

    conv = _C.objects.filter(pk=(data.get("conv") or "")).select_related("user").first()
    if conv is None:
        return JsonResponse({"error": "not_found"}, status=404)

    action = (data.get("action") or "").strip()

    if action == "take":
        # Taking over without typing yet. Useful on its own: it silences the AI
        # immediately, so the customer is not answered by a robot in the seconds
        # it takes to read the thread and write something human.
        conv.owner_joined = True
        conv.timeout_notified = True
        conv.save(update_fields=["owner_joined", "timeout_notified", "updated_at"])
        return JsonResponse({"ok": True, "owner_joined": True})

    if action == "release":
        conv.owner_joined = False
        # Back to open, and the waiting notice is suppressed for good: a person
        # did turn up, so telling the customer nobody was available would be
        # false.
        conv.status = _C.Status.OPEN
        conv.timeout_notified = True
        _M.objects.create(conversation=conv, role=_M.Role.ASSISTANT, content=RESUME_MESSAGE)
        conv.user_unread = (conv.user_unread or 0) + 1
        conv.save(update_fields=["owner_joined", "status", "timeout_notified",
                                 "user_unread", "updated_at"])
        return JsonResponse({"ok": True, "owner_joined": False})

    if action == "close":
        conv.status = _C.Status.CLOSED
        conv.save(update_fields=["status", "updated_at"])
        return JsonResponse({"ok": True, "closed": True})

    text = (data.get("message") or "").strip()[:4000]
    if not text:
        return JsonResponse({"error": "empty"}, status=400)

    message = _M.objects.create(conversation=conv, role=_M.Role.OWNER, content=text)
    conv.owner_joined = True
    conv.timeout_notified = True
    conv.user_unread = (conv.user_unread or 0) + 1
    conv.save(update_fields=["owner_joined", "timeout_notified", "user_unread", "updated_at"])
    return JsonResponse({"ok": True, "owner_joined": True, "message": _message_json(message)})
