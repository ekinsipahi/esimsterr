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
    """Deliver the profile to whoever is actually travelling.

    For a gift that is the recipient, not the buyer -- sending the QR to the
    person who paid and asking them to forward it defeats the point and leaks
    the activation code through one more inbox than it needs to."""
    send_email_bg(
        order.delivery_email,
        f"Your {order.plan_title} eSIM is ready — install it now",
        "esim_ready", {"order": order, "esim": esim, "is_gift": order.is_gift},
    )
    if order.is_gift:
        # The buyer gets a receipt, not the activation code.
        send_email_bg(
            order.email,
            f"Your gift is on its way to {order.gift_email}",
            "gift_sent", {"order": order},
        )


def send_balance_added(topup):
    """Receipt for store credit. Sent even though nothing was delivered: money
    left the customer's account, so there has to be a record they can find."""
    send_email_bg(
        topup.user.email,
        f"You added {topup.amount_usd:.2f} USD to your {settings.SITE_NAME} balance",
        "balance_added", {"topup": topup, "wallet": topup.user.wallet},
    )


def send_referral_reward(referrer, referred, amount):
    """Tell somebody their invitation paid off. This is the email that makes the
    next invitation happen, so it goes out the moment the credit lands."""
    send_email_bg(
        referrer.email,
        f"You earned {amount} USD — {referred.email.split('@')[0]} joined {settings.SITE_NAME}",
        "referral_reward",
        {"referrer": referrer, "referred_email": referred.email, "amount": amount,
         "code": referrer.referral_code or ""},
    )


def send_password_reset(user, reset_url):
    send_email_bg(user.email, "Reset your password", "password_reset", {"user": user, "reset_url": reset_url})


def notify_admin(subject, lines):
    """Plain-text heads-up to ADMIN_NOTIFY_EMAILS (new order, fulfilment failure...)."""
    for to in settings.ADMIN_NOTIFY_EMAILS:
        send_email_bg(to, f"[{settings.SITE_NAME}] {subject}", "admin_notice",
                      {"subject": subject, "lines": lines})
