"""The public coupons page and the endpoint checkout calls to test a code.

The page exists for a real search intent: people look for "eSIM discount code"
before they buy, and if we do not give them somewhere to land, a coupon-scraper
site does it for us and takes a cut.
"""
from __future__ import annotations

import json
import logging

from django.conf import settings
from django.http import JsonResponse
from django.shortcuts import render
from django.utils import translation
from django.utils.translation import gettext as _
from django.views.decorators.http import require_POST

from apps.catalog.models import Plan
from core.ratelimit import client_ip, rate_limit

from .models import ZERO, money
from .services import IDENTITY_REASONS, CouponError, public_coupons, validate_coupon

log = logging.getLogger(__name__)


def _faq():
    return [
        (_("How do I use an eSIMsterr coupon code?"),
         _("Choose your plan, then paste the code into the coupon box on the checkout page "
           "and apply it. The new total is shown before you pay, so you never have to take "
           "the discount on trust.")),
        (_("Does every code work on every plan?"),
         _("Each code carries its own conditions and they are printed on the card above. "
           "Most work on any country or regional plan; some ask for a minimum order or are "
           "limited to a first purchase.")),
        (_("Can I use two codes on one order?"),
         _("No. One code per order. If you are buying several eSIMs, use the code on each "
           "order separately where its conditions allow it.")),
        (_("Why are the prices already lower than the big eSIM apps?"),
         _("Because we do not buy app-install ads, and on the well-known apps that marketing "
           "spend is a large part of what you pay for. The coupon comes off a price that is "
           "already cut close.")),
        (_("Do these codes expire?"),
         _("Some do. Any end date is printed on the coupon card. An expired code is refused "
           "at checkout with a clear message rather than quietly ignored.")),
        (_("My code was refused. What should I check?"),
         _("Read the conditions on the card: a minimum order, first order only, or one use "
           "per customer. If the code still will not apply, contact support with the code and "
           "your email address and we will make it right.")),
        (_("Do I need an account to use a coupon?"),
         _("No. Guest checkout accepts codes too. We only need an email address to send the "
           "QR code to, which is also how a one-per-customer code is counted.")),
    ]


def _faq_jsonld(items):
    return json.dumps({
        "@context": "https://schema.org",
        "@type": "FAQPage",
        "mainEntity": [
            {"@type": "Question", "name": str(q),
             "acceptedAnswer": {"@type": "Answer", "text": str(a)}}
            for q, a in items
        ],
    }, ensure_ascii=False)


def coupons_page(request):
    coupons = public_coupons()
    copy_language = settings.LANGUAGE_CODE
    active_language = translation.get_language() or copy_language
    copy_is_foreign = active_language.split("-")[0] != copy_language.split("-")[0]
    # The headline number is whatever we actually offer today, never a decorative
    # figure: a title promising 20% that checkout then refuses is a broken promise.
    best_pct = max((c.percent_off or 0 for c in coupons), default=0)
    faq = _faq()

    if best_pct:
        seo_title = _("eSIM coupon codes — %(pct)s%% off travel data | %(site)s") % {
            "pct": best_pct, "site": settings.SITE_NAME,
        }
        seo_description = _(
            "Working eSIM discount codes for %(site)s: up to %(pct)s%% off prepaid travel data "
            "in 150+ countries. Copy a code, paste it at checkout, see the new total before "
            "you pay."
        ) % {"site": settings.SITE_NAME, "pct": best_pct}
    else:
        seo_title = _("eSIM coupon codes and discounts | %(site)s") % {"site": settings.SITE_NAME}
        seo_description = _(
            "Current eSIM discount codes for %(site)s, plus how to apply one at checkout. "
            "Prepaid travel data in 150+ countries, cheaper than roaming."
        ) % {"site": settings.SITE_NAME}

    return render(request, "coupons/index.html", {
        "coupons": coupons,
        "best_pct": best_pct,
        # Offer descriptions are operator-written campaign copy held in the
        # database, so they stay in the shop's own language whatever the visitor
        # is reading. The page marks them as such rather than passing them off as
        # translated: a lang attribute is what tells a screen reader to switch
        # voice and a browser to offer a translation.
        "copy_language": copy_language,
        "copy_is_foreign": copy_is_foreign,
        "faq": faq,
        "faq_jsonld": _faq_jsonld(faq),
        "breadcrumbs": [(_("Home"), "/"), (_("Coupons"), None)],
        "seo_title": seo_title,
        "seo_description": seo_description,
    })


def _body(request) -> dict:
    """Accept a JSON body or a normal form post; the checkout page may send either."""
    if (request.content_type or "").split(";")[0].strip() == "application/json":
        try:
            data = json.loads(request.body.decode("utf-8") or "{}")
        except (ValueError, UnicodeDecodeError):
            return {}
        return data if isinstance(data, dict) else {}
    return request.POST.dict()


def _owns_address(request, email: str) -> bool:
    """True when the caller has proved they read the mailbox they are asking about.

    Signing in is that proof here only in the weak sense that it is the best we
    have: an address the caller typed into the body of an anonymous request is
    proof of nothing at all.
    """
    if not request.user.is_authenticated:
        return False
    return not email or email == (request.user.email or "").strip().lower()


@require_POST
@rate_limit("coupon", 20, 3600)
def validate_api(request):
    """Live check for the checkout page: {code, plan_id, email} -> price after discount.

    The amount is always taken from the plan in our database, never from the
    request body, so a crafted post cannot talk us into a bigger discount.
    """
    data = _body(request)
    code = str(data.get("code") or "")[:32]
    email = str(data.get("email") or "").strip().lower()[:254]

    try:
        plan_id = int(data.get("plan_id") or 0)
    except (TypeError, ValueError):
        plan_id = 0
    plan = Plan.objects.live().filter(pk=plan_id).first() if plan_id else None
    if plan is None:
        return JsonResponse({
            "ok": False, "code": "", "discount_usd": "0.00", "total_usd": "0.00",
            "message": _("We could not find that plan. Please reload the page."),
        }, status=400)

    amount = money(plan.price)
    try:
        coupon, discount = validate_coupon(
            code, amount_usd=amount, plan=plan,
            user=request.user if request.user.is_authenticated else None,
            email=email or (request.user.email if request.user.is_authenticated else ""),
        )
    except CouponError as e:
        message = str(e)
        if e.reason in IDENTITY_REASONS and not _owns_address(request, email):
            # "You have already used this code" and "first order only" both answer
            # the question "has this address bought from us", to anyone who can
            # post an email address. Say nothing useful; keep the reason in the log.
            log.info(
                "coupon %s refused for %s (%s) from %s",
                code, email or "-", e.reason, client_ip(request),
            )
            message = _("This code cannot be applied to this order.")
        return JsonResponse({
            "ok": False, "code": "", "discount_usd": "0.00", "total_usd": f"{amount}",
            "message": message,
        })

    return JsonResponse({
        "ok": True,
        "code": coupon.code,
        "discount_usd": f"{discount}",
        "total_usd": f"{max(amount - discount, ZERO)}",
        "message": _("%(label)s applied. You save $%(amount)s.") % {
            "label": coupon.public_label, "amount": discount,
        },
    })
