"""Balance pages.

Top-up happens here, on the website, in a browser — including when the customer
started in the app. That is not a limitation to work around: a payment taken
inside a store app is the thing both app stores have rules about, and credit
bought on the web and merely *spent* in the app is not a payment transaction at
all. The mobile client opens these pages in the system browser.
"""
from __future__ import annotations

import logging

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import Http404
from django.shortcuts import redirect, render
from django.utils.translation import gettext as _
from django.views.decorators.http import require_POST

from apps.payments import services as payment_services
from core.ratelimit import client_ip, rate_limit

from .models import BalanceTopUp, Wallet
from .services import limits, presets, validate_amount, create_topup

log = logging.getLogger(__name__)


def _enabled():
    if not getattr(settings, "WALLET_ENABLED", True):
        raise Http404
    return True


@login_required
def wallet(request):
    _enabled()
    w = Wallet.for_user(request.user)
    low, high = limits()
    added = request.GET.get("added")
    if added:
        topup = BalanceTopUp.objects.filter(ref=added, user=request.user).first()
        if topup and topup.status == BalanceTopUp.Status.CREDITED:
            messages.success(request, _("Added %(total)s to your balance.") % {
                "total": f"${topup.credited_usd}"})
        elif topup:
            # The webhook may still be in flight; say so rather than showing an
            # unchanged balance and letting them think the money vanished.
            messages.info(request, _("Your payment is confirming. The balance updates "
                                     "within a minute — refresh the page."))
    return render(request, "wallet/wallet.html", {
        "wallet": w,
        "presets": presets(),
        "transactions": w.transactions.select_related("order")[:40],
        "min_topup": low, "max_topup": high,
        "stripe_enabled": bool(settings.STRIPE_SECRET_KEY),
        "crypto_enabled": bool(settings.NOWPAYMENTS_API_KEY),
        "seo_title": _("Your balance — %(site)s") % {"site": settings.SITE_NAME},
        "meta_robots": "noindex,nofollow",
    })


@login_required
@rate_limit("wallet_add", limit=10, window=3600)
def wallet_add(request):
    _enabled()
    w = Wallet.for_user(request.user)
    low, high = limits()
    error = ""
    amount = request.POST.get("amount") or request.GET.get("amount") or ""

    if request.method == "POST":
        method = request.POST.get("method") or "stripe"
        try:
            validate_amount(amount)
        except ValueError as e:
            error = str(e)
        else:
            topup = create_topup(request.user, amount,
                                 source=(request.POST.get("source") or "web"),
                                 ip=client_ip(request))
            try:
                url = payment_services.start_balance_payment(topup, method, request)
            except payment_services.PaymentError as e:
                topup.status = BalanceTopUp.Status.FAILED
                topup.save(update_fields=["status"])
                error = str(e)
            else:
                return redirect(url)

    return render(request, "wallet/add.html", {
        "wallet": w,
        "presets": presets(),
        "amount": amount,
        "error": error,
        "min_topup": low, "max_topup": high,
        "stripe_enabled": bool(settings.STRIPE_SECRET_KEY),
        "crypto_enabled": bool(settings.NOWPAYMENTS_API_KEY),
        "seo_title": _("Add balance — %(site)s") % {"site": settings.SITE_NAME},
        "meta_robots": "noindex,nofollow",
    })
