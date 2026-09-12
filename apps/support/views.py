"""Support views: the public help centre and ticket thread (guests included),
plus the JSON endpoint behind the assistant widget.

Two different doors on purpose. Tickets are open to anyone who bought without an
account -- that is most of our buyers -- and are protected by a signed link.
The assistant costs money per message, so it is behind a login and behind
per-account and per-IP hourly caps.
"""
from __future__ import annotations

import json
import logging

from django.conf import settings
from django.contrib import messages as flash
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.core.validators import validate_email, validate_ipv46_address
from django.db import IntegrityError
from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.translation import gettext as _
from django.utils.translation import gettext_lazy as _lazy
from django.views.decorators.csrf import ensure_csrf_cookie

from apps.accounts.emails import notify_admin, send_email_bg
from core.ratelimit import client_ip, rate_limit

from . import assistant as brain
from .models import AssistantConversation, AssistantMessage, Ticket, TicketMessage

log = logging.getLogger(__name__)

BODY_MAX = 5000
SUBJECT_MAX = 160
MAX_OPEN_TICKETS = 10


def _ip(request):
    """X-Forwarded-For is whatever the caller typed. A GenericIPAddressField is
    an inet column on PostgreSQL, so junk in that header aborts the INSERT and
    the customer loses the ticket they just wrote; anything that is not an
    address is stored as nothing at all."""
    ip = client_ip(request)
    if not ip or ip == "unknown":
        return None
    try:
        validate_ipv46_address(ip)
    except ValidationError:
        return None
    return ip


def _reply_to() -> str:
    """Where a customer's plain "reply" lands: the operator inbox, not the
    no-reply sender."""
    return getattr(settings, "SUPPORT_FORWARD_EMAIL", "") or settings.SUPPORT_EMAIL


def _ua(request) -> str:
    return (request.META.get("HTTP_USER_AGENT", "") or "")[:300]


def _create_ticket(**fields) -> Ticket | None:
    """Create with a fresh reference, retrying the (astronomically unlikely)
    collision rather than 500-ing on a customer who is already annoyed."""
    for _attempt in range(5):
        try:
            return Ticket.objects.create(ref=Ticket.new_ref(), **fields)
        except IntegrityError:
            continue
    return None


def _notify_new_ticket(ticket, body):
    notify_admin(
        f"New ticket {ticket.ref}: {ticket.subject}",
        [f"From: {ticket.email}" + (" (account)" if ticket.user_id else " (guest)"),
         f"Category: {ticket.get_category_display()}",
         f"Order: {ticket.order_ref or '-'}",
         f"ICCID: {ticket.iccid or '-'}",
         f"IP: {ticket.ip or '-'}",
         f"Link: {settings.SITE_URL}{ticket.guest_url}",
         "", body],
    )


def _support_page(request, form=None):
    """The help centre. `form` carries the posted values back so a rejected
    ticket is re-rendered with the customer's own words still in the box."""
    return render(request, "pages/support.html", {
        "categories": Ticket.Category.choices,
        "my_tickets": list(request.user.tickets.all()[:10]) if request.user.is_authenticated else [],
        "form": form or {},
        "breadcrumbs": [(_("Home"), "/"), (_("Support"), None)],
        "seo_title": _("Support — %(site)s") % {"site": settings.SITE_NAME},
        "seo_description": _("Fix eSIM installation, activation and no-data problems, or open a "
                             "support ticket. Guests can use their order reference."),
    })


# --- Help centre + ticket form ----------------------------------------------
@rate_limit("support", limit=5, window=3600)
def support(request):
    if request.method == "POST":
        email = (request.POST.get("email") or "").strip().lower()
        if request.user.is_authenticated:
            email = (request.user.email or email).strip().lower()
        subject = (request.POST.get("subject") or "").strip()[:SUBJECT_MAX]
        body = (request.POST.get("body") or "").strip()[:BODY_MAX]
        category = (request.POST.get("category") or Ticket.Category.OTHER).strip()
        order_ref = (request.POST.get("order_ref") or "").strip().upper()[:12]
        iccid = "".join(c for c in (request.POST.get("iccid") or "") if c.isdigit())[:32]

        if category not in Ticket.Category.values:
            category = Ticket.Category.OTHER
        posted = {"email": email, "subject": subject, "body": body, "category": category,
                  "order_ref": order_ref, "iccid": iccid}

        try:
            validate_email(email)
        except ValidationError:
            flash.error(request, _("Please enter a valid email address so we can reply."))
            return _support_page(request, posted)
        if not subject or len(body) < 10:
            flash.error(request, _("Add a subject and a few sentences so we can help properly."))
            return _support_page(request, posted)
        if request.user.is_authenticated and \
                request.user.tickets.exclude(status=Ticket.Status.CLOSED).count() >= MAX_OPEN_TICKETS:
            flash.error(request, _("You already have several open tickets. Reply on one of those and "
                                   "we will pick it up there."))
            return _support_page(request, posted)

        ticket = _create_ticket(
            user=request.user if request.user.is_authenticated else None,
            email=email, subject=subject, category=category,
            order_ref=order_ref, iccid=iccid,
            ip=_ip(request), user_agent=_ua(request),
        )
        if ticket is None:
            flash.error(request, _("Something went wrong on our side. Please try once more."))
            return _support_page(request, posted)

        TicketMessage.objects.create(ticket=ticket, role=TicketMessage.Role.USER, body=body)
        # Subject stays plain English like the rest of the mail shell: the body is
        # rendered in a background thread with no active language.
        send_email_bg(
            email, f"We have your message ({ticket.ref})",
            "ticket_opened",
            {"ticket": ticket, "body": body,
             "ticket_url": f"{settings.SITE_URL}{ticket.guest_url}"},
            reply_to=_reply_to(),
        )
        _notify_new_ticket(ticket, body)

        flash.success(request, _("Thanks — your reference is %(ref)s. We reply by email, usually "
                                 "within a few hours.") % {"ref": ticket.ref})
        # The guest link carries the signed token; the account holder gets the
        # plain URL because their session already proves who they are.
        return redirect(ticket.get_absolute_url() if request.user.is_authenticated
                        else ticket.guest_url)

    return _support_page(request)


# --- One ticket thread -------------------------------------------------------
def _may_see(request, ticket) -> bool:
    """Owning the account the ticket is attached to, holding the signed link we
    mailed, or being staff. Matching email addresses is deliberately NOT enough:
    signup takes an address and signs the user straight in without ever mailing
    it, so anyone can register as somebody else and this thread carries their
    order reference, ICCID and support history."""
    if request.user.is_authenticated:
        if ticket.user_id and ticket.user_id == request.user.id:
            return True
        if request.user.is_staff:
            return True
    token = request.GET.get("t") or request.POST.get("t") or ""
    return Ticket.check_token(token, ticket.ref, ticket.email)


@rate_limit("ticket_reply", limit=20, window=3600)
def ticket_detail(request, ref):
    ticket = get_object_or_404(Ticket, ref=ref.upper())
    if not _may_see(request, ticket):
        # 404, not 403: never confirm that a reference exists to someone who
        # cannot open it.
        raise Http404

    token = request.GET.get("t") or request.POST.get("t") or ""
    back = ticket.get_absolute_url() + (f"?t={token}" if token and not request.user.is_authenticated else "")

    if request.method == "POST":
        if (request.POST.get("action") or "reply") == "close":
            ticket.status = Ticket.Status.CLOSED
            ticket.save(update_fields=["status", "updated_at"])
            flash.success(request, _("Ticket closed. Reply any time to open it again."))
            return redirect(back)

        body = (request.POST.get("body") or "").strip()[:BODY_MAX]
        if not body:
            flash.error(request, _("Write a message first."))
            return redirect(back)

        TicketMessage.objects.create(ticket=ticket, role=TicketMessage.Role.USER, body=body)
        # A customer reply reopens the thread: "answered" means we are waiting
        # on them, and that is no longer true.
        ticket.status = Ticket.Status.OPEN
        ticket.save(update_fields=["status", "updated_at"])
        notify_admin(
            f"Reply on {ticket.ref}: {ticket.subject}",
            [f"From: {ticket.email}",
             f"Link: {settings.SITE_URL}{ticket.guest_url}", "", body],
        )
        flash.success(request, _("Sent. We reply by email."))
        return redirect(back)

    return render(request, "support/ticket_detail.html", {
        "ticket": ticket,
        "thread": ticket.messages.all(),
        "token": token if not request.user.is_authenticated else "",
        "breadcrumbs": [(_("Support"), "/support/"), (ticket.ref, None)],
        "seo_title": _("Ticket %(ref)s") % {"ref": ticket.ref},
        "meta_robots": "noindex,nofollow",
    })


# --- Assistant chat API ------------------------------------------------------
MSG_MAX = 2000
RATE_PER_HOUR_USER = 30
RATE_PER_HOUR_IP = 90

# Module-level, so it must be lazy: the active language is only known per request.
FALLBACK_REPLY = _lazy(
    "I could not reach the assistant just now and the team has been told. If it is urgent, "
    "open a ticket on the support page and we will answer by email."
)


def _active_conversation(request, create=False):
    conv = (AssistantConversation.objects
            .exclude(status=AssistantConversation.Status.CLOSED)
            .filter(user=request.user).order_by("-updated_at").first())
    if conv is None and create:
        conv = AssistantConversation.objects.create(
            user=request.user, ip=_ip(request), user_agent=_ua(request),
        )
    return conv


def _serialize(conv, mark_seen=False) -> dict:
    if conv is None:
        return {"id": None, "status": "open", "owner_joined": False,
                "messages": [], "unread": 0}
    unread = conv.user_unread or 0
    # The badge poll must NOT clear the counter; only an open panel (seen=1) does.
    if mark_seen and unread:
        # Clear only the count we are about to show. An operator reply that
        # landed between reading the row and writing it back must survive, or
        # the customer never sees a badge for it.
        cleared = (AssistantConversation.objects
                   .filter(pk=conv.pk, user_unread__lte=unread)
                   .update(user_unread=0))
        if cleared:
            conv.user_unread = unread = 0
        else:
            conv.refresh_from_db(fields=["user_unread"])
            unread = conv.user_unread or 0
    return {
        "id": str(conv.id),
        "status": conv.status,
        "owner_joined": conv.owner_joined,
        "unread": unread,
        "messages": [{"role": m.role, "content": m.content,
                      "created_at": m.created_at.isoformat()}
                     for m in conv.messages.all()],
    }


def _rate_limited(request) -> bool:
    """Hourly caps per account and per IP. One person with ten accounts still
    hits the IP ceiling, and the cache being down never blocks a customer."""
    hour = timezone.now().strftime("%Y%m%d%H")
    k_user = f"asst:u{request.user.pk}:{hour}"
    k_ip = f"asst:ip{client_ip(request)}:{hour}"
    try:
        c_user = cache.get_or_set(k_user, 0, 3700)
        c_ip = cache.get_or_set(k_ip, 0, 3700)
        if c_user >= RATE_PER_HOUR_USER or c_ip >= RATE_PER_HOUR_IP:
            return True
        cache.incr(k_user)
        cache.incr(k_ip)
    except Exception:  # noqa: BLE001
        pass
    return False


@ensure_csrf_cookie
def assistant_api(request):
    """GET returns the live thread (?seen=1 clears the unread badge);
    POST appends a message and returns the updated thread.

    Sign-in is required. This endpoint spends money on every POST, so hiding the
    widget would not be protection -- the login is.
    """
    if not settings.ASSISTANT_ENABLED:
        # The kill switch has to reach the endpoint too: dropping the widget
        # leaves the URL live, and every POST to it still buys an LLM call.
        return JsonResponse(
            {"error": "disabled",
             "detail": _("The assistant is off right now. Open a support ticket and we will "
                         "answer by email.")},
            status=503,
        )

    if not request.user.is_authenticated:
        # JSON, not a redirect: the widget's fetch would otherwise receive the
        # login page HTML and try to parse it.
        return JsonResponse(
            {"error": "login_required",
             "detail": _("Sign in to chat with the assistant. Guests can open a support ticket "
                         "instead.")},
            status=401,
        )

    if request.method == "GET":
        conv = _active_conversation(request)
        return JsonResponse(_serialize(conv, mark_seen=request.GET.get("seen") == "1"))
    if request.method != "POST":
        return JsonResponse({"error": "method_not_allowed"}, status=405)

    try:
        data = json.loads(request.body.decode() or "{}")
        if not isinstance(data, dict):
            data = {}
    except (ValueError, UnicodeDecodeError):
        data = request.POST  # a plain form post still works
    text = (data.get("message") or "").strip()[:MSG_MAX]
    if not text:
        return JsonResponse({"error": "empty"}, status=400)
    if _rate_limited(request):
        return JsonResponse(
            {"error": "rate_limited",
             "detail": _("That is a lot of messages in one hour. Give it a few minutes, or open a "
                         "ticket and we will answer by email.")},
            status=429,
        )

    conv = _active_conversation(request, create=True)
    if not conv.ip:
        conv.ip, conv.user_agent = _ip(request), _ua(request)

    flags = brain.detect_intent(text)
    AssistantMessage.objects.create(
        conversation=conv, role=AssistantMessage.Role.USER,
        content=text, intent=",".join(sorted(flags)),
    )

    newly_escalated = False
    if flags:
        conv.add_flags(flags)
        if (flags & brain.ESCALATE_FLAGS) and conv.status != AssistantConversation.Status.ESCALATED:
            conv.status = AssistantConversation.Status.ESCALATED
            conv.escalated_at = timezone.now()
            newly_escalated = True
    # Named fields only: a full save would write this request's stale copy of
    # user_unread back over an operator reply counted a moment ago.
    conv.save(update_fields=["ip", "user_agent", "intent_flags", "status",
                             "escalated_at", "updated_at"])

    if newly_escalated:
        hit = sorted(flags & brain.ESCALATE_FLAGS)
        for to in settings.ADMIN_NOTIFY_EMAILS:
            send_email_bg(
                to, f"[{settings.SITE_NAME}] Chat escalated: {', '.join(hit)}",
                "assistant_escalation",
                {"conversation": conv, "who": request.user.email, "message": text,
                 "flags": hit,
                 "admin_url": f"{settings.SITE_URL}/admin/support/assistantconversation/{conv.id}/change/"},
            )

    # Operator takeover: the AI goes quiet and a human writes the next reply.
    if conv.owner_joined:
        return JsonResponse(_serialize(conv, mark_seen=True))

    history = [
        {"role": "user" if m.role == AssistantMessage.Role.USER else "assistant",
         "content": m.content}
        for m in conv.messages.exclude(role=AssistantMessage.Role.OWNER)
    ]
    reply = brain.generate_reply(history, brain.build_user_context(request.user)) or str(FALLBACK_REPLY)
    AssistantMessage.objects.create(
        conversation=conv, role=AssistantMessage.Role.ASSISTANT, content=reply,
    )
    # Only the timestamp, so the admin list sorts by real activity; see above.
    conv.save(update_fields=["updated_at"])
    return JsonResponse(_serialize(conv, mark_seen=True))
