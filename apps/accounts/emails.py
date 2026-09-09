"""Transactional emails. Always sent in a background thread so a slow mail API
never blocks a checkout/webhook. Failures are logged, never raised."""
from __future__ import annotations

import logging
import threading

from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string

log = logging.getLogger(__name__)


def _send_now(to, subject, template, ctx, reply_to=None):
    ctx = {"site_name": settings.SITE_NAME, "site_url": settings.SITE_URL,
           "support_email": settings.SUPPORT_EMAIL, **ctx}
    html = render_to_string(f"emails/{template}.html", ctx)
    text = render_to_string(f"emails/{template}.txt", ctx)
    msg = EmailMultiAlternatives(subject, text, settings.DEFAULT_FROM_EMAIL, [to],
                                 reply_to=[reply_to] if reply_to else None)
    msg.attach_alternative(html, "text/html")
    msg.send(fail_silently=False)


def send_email_bg(to, subject, template, ctx, reply_to=None):
    if not (to or "").strip():
        return

    def _run():
        from django.db import connections
        try:
            _send_now(to, subject, template, ctx, reply_to)
        except Exception as e:  # noqa: BLE001
            log.warning("[MAIL] failed to=%s subject=%r: %s", to, subject, e)
        finally:
            connections.close_all()

    threading.Thread(target=_run, daemon=True).start()


def send_welcome(user):
    send_email_bg(user.email, f"Welcome to {settings.SITE_NAME}", "welcome", {"user": user})


def send_esim_ready(order, esim):
    send_email_bg(
        order.email, f"Your {order.plan_title} eSIM is ready — install it now",
        "esim_ready", {"order": order, "esim": esim},
    )


def send_password_reset(user, reset_url):
    send_email_bg(user.email, "Reset your password", "password_reset", {"user": user, "reset_url": reset_url})


def notify_admin(subject, lines):
    """Plain-text heads-up to ADMIN_NOTIFY_EMAILS (new order, fulfilment failure...)."""
    for to in settings.ADMIN_NOTIFY_EMAILS:
        send_email_bg(to, f"[{settings.SITE_NAME}] {subject}", "admin_notice",
                      {"subject": subject, "lines": lines})
