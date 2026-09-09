from django.conf import settings
from django.contrib import messages
from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.shortcuts import get_object_or_404, redirect, render

from apps.accounts.emails import notify_admin, send_email_bg
from core.ratelimit import rate_limit

from .models import Ticket


@rate_limit("support", limit=5, window=3600)
def support(request):
    """Public help centre + ticket form (works for guests too)."""
    if request.method == "POST":
        email = (request.POST.get("email") or
                 (request.user.email if request.user.is_authenticated else "")).strip().lower()
        subject = (request.POST.get("subject") or "").strip()[:160]
        body = (request.POST.get("body") or "").strip()
        category = request.POST.get("category") or Ticket.Category.OTHER
        try:
            validate_email(email)
        except ValidationError:
            messages.error(request, "Please enter a valid email address.")
            return redirect("support")
        if len(body) < 10 or not subject:
            messages.error(request, "Add a subject and a few sentences so we can help properly.")
            return redirect("support")

        ticket = Ticket.objects.create(
            user=request.user if request.user.is_authenticated else None,
            email=email, subject=subject, body=body, category=category,
            iccid=(request.POST.get("iccid") or "").strip()[:32],
            order_ref=(request.POST.get("order_ref") or "").strip()[:12],
        )
        notify_admin(
            f"New ticket {ticket.ref}: {subject}",
            [f"From: {email}", f"Category: {ticket.get_category_display()}",
             f"ICCID: {ticket.iccid or '—'}", f"Order: {ticket.order_ref or '—'}", "", body],
        )
        send_email_bg(email, f"We got your message ({ticket.ref})", "ticket_received",
                      {"ticket": ticket}, reply_to=settings.SUPPORT_EMAIL)
        messages.success(request, f"Thanks — your ticket is {ticket.ref}. We reply by email, usually within a few hours.")
        return redirect("support")

    return render(request, "pages/support.html", {
        "categories": Ticket.Category.choices,
        "seo_title": f"Support — {settings.SITE_NAME}",
        "seo_description": "Get help with eSIM installation, activation, coverage, payments and refunds.",
    })
