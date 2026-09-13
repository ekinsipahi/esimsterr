"""Checkout + customer dashboard (server-rendered)."""
from __future__ import annotations

import io
import logging

from decimal import Decimal

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.validators import validate_email
from django.core.exceptions import ValidationError
from django.http import Http404, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.translation import gettext_lazy as _
from django.views.decorators.http import require_POST

from core.ratelimit import rate_limit

from apps.catalog.models import Plan
from apps.common import analytics
from apps.coupons.services import CouponError, redeem, release, validate_coupon
from apps.payments import services as payment_services
from apps.providers.yesim import YesimError

from .models import Esim, Order
from .services import sync_esim

log = logging.getLogger(__name__)

# A guest's order refs live in the session so they can reopen the QR page
# without an account (they still get the email).
SESSION_ORDERS = "guest_order_refs"


def _client_ip(request):
    xff = request.META.get("HTTP_X_FORWARDED_FOR", "")
    return (xff.split(",")[0].strip() if xff else request.META.get("REMOTE_ADDR")) or None


def _fingerprint(request) -> dict:
    """Request provenance stored on every order.

    Most buyers never create an account, so without this a guest order is an
    email address and nothing else. These four fields are what makes a
    chargeback defensible and lets the operator spot one person working through
    disposable inboxes."""
    return {
        "ip": _client_ip(request),
        "user_agent": request.META.get("HTTP_USER_AGENT", "")[:300],
        "accept_language": request.META.get("HTTP_ACCEPT_LANGUAGE", "")[:120],
        "referrer": request.META.get("HTTP_REFERER", "")[:300],
    }


def _remember_order(request, order):
    refs = request.session.get(SESSION_ORDERS, [])
    if order.ref not in refs:
        refs.append(order.ref)
        request.session[SESSION_ORDERS] = refs[-20:]


def _can_view_order(request, order):
    if request.user.is_authenticated and order.user_id == request.user.id:
        return True
    if request.user.is_staff:
        return True
    return order.ref in request.session.get(SESSION_ORDERS, [])


@rate_limit("checkout", limit=12, window=3600)
def checkout(request, plan_id):
    """Plan summary, optional coupon, email and payment method.

    Creates the order, reserves the coupon seat, then hands off to Stripe
    Checkout or a NOWPayments invoice. If the handoff fails the seat is released
    immediately so an unreachable payment provider cannot burn a capped code."""
    plan = get_object_or_404(
        Plan.objects.live().select_related("country", "region"), pk=plan_id
    )
    topup_esim = None
    esim_pk = request.GET.get("esim") or request.POST.get("esim")
    if esim_pk:
        topup_esim = Esim.objects.filter(pk=esim_pk).first()
        if topup_esim and request.user.is_authenticated and topup_esim.user_id != request.user.id:
            topup_esim = None

    email = request.user.email if request.user.is_authenticated else ""
    code = (request.GET.get("coupon") or "").strip()
    error = None
    coupon = None
    discount = Decimal("0.00")
    subtotal = Decimal(plan.price)

    # "Apply" re-renders the page with the coupon priced in; it must never create
    # an order or start a payment.
    apply_only = request.method == "POST" and "apply_only" in request.POST

    if request.method == "POST":
        email = (request.POST.get("email") or email).strip().lower()
        code = (request.POST.get("coupon") or "").strip()
        method = request.POST.get("method") or "stripe"
        try:
            validate_email(email)
        except ValidationError:
            if not apply_only:
                error = _("Please enter a valid email address. This is where your QR code goes.")
            email = ""

        if not error and code:
            try:
                coupon, discount = validate_coupon(
                    code, amount_usd=subtotal, plan=plan,
                    user=request.user if request.user.is_authenticated else None,
                    email=email,
                )
            except CouponError as e:
                # Deliberately stop here rather than quietly charging full price.
                # Someone who typed a code expects the discount; taking their
                # money without it is the kind of surprise that becomes a
                # chargeback. They can clear the field and pay, or fix the code.
                coupon, discount = None, Decimal("0.00")
                error = _("%(reason)s Clear the coupon field to continue at the "
                          "normal price.") % {"reason": e}

        if not error and not apply_only:
            total = (subtotal - discount).quantize(Decimal("0.01"))
            order = Order.objects.create(
                user=request.user if request.user.is_authenticated else None,
                email=email,
                kind=Order.Kind.TOPUP if topup_esim else Order.Kind.NEW,
                plan=plan,
                plan_title=plan.title,
                plan_provider_id=plan.provider_plan_id,
                plan_days=plan.days,
                plan_data_label=plan.data_label,
                subtotal_usd=subtotal,
                discount_usd=discount,
                amount_usd=total,
                coupon=coupon,
                coupon_code=coupon.code if coupon else "",
                cost_amount=plan.cost_amount,
                cost_currency=plan.cost_currency,
                target_esim=topup_esim,
                **_fingerprint(request),
            )
            _remember_order(request, order)
            if coupon is not None:
                try:
                    redeem(coupon, order,
                           user=request.user if request.user.is_authenticated else None,
                           email=email, ip=order.ip)
                except CouponError as e:
                    order.coupon, order.coupon_code = None, ""
                    order.discount_usd = Decimal("0.00")
                    order.amount_usd = subtotal
                    order.save(update_fields=["coupon", "coupon_code", "discount_usd", "amount_usd"])
                    error = str(e)

            if not error:
                try:
                    url = payment_services.start_payment(order, method, request)
                except payment_services.PaymentError as e:
                    release(order)
                    order.status = Order.Status.FAILED
                    order.save(update_fields=["status"])
                    error = str(e)
                else:
                    return redirect(url)

    elif code:
        # Coupon arrived in the URL (a campaign link). Preview it without an
        # email; per-customer rules are re-checked on POST anyway.
        try:
            coupon, discount = validate_coupon(
                code, amount_usd=subtotal, plan=plan,
                user=request.user if request.user.is_authenticated else None,
                email=email,
            )
        except CouponError:
            coupon, discount = None, Decimal("0.00")

    events = [analytics.begin_checkout(plan, coupon=(coupon.code if coupon else ""),
                                       value=(subtotal - discount))]
    if request.method == "POST" and not apply_only:
        # They chose a method and pressed pay; the redirect leaves our site, so
        # this is the last moment we can report it.
        events.append(analytics.add_payment_info(
            plan, request.POST.get("method") or "stripe",
            coupon=(coupon.code if coupon else ""), value=(subtotal - discount)))

    ctx = {
        "plan": plan,
        "topup_esim": topup_esim,
        "email": email,
        "coupon_code": code,
        "analytics_events": events,
        "coupon": coupon,
        "discount": discount,
        "subtotal": subtotal,
        "total": (subtotal - discount).quantize(Decimal("0.01")),
        "error": error,
        "seo_title": _("Checkout"),
        "meta_robots": "noindex,nofollow",
        "breadcrumbs": [
            (_("Home"), "/"),
            (plan.target_name, plan.target.get_absolute_url() if plan.target else "/"),
            (_("Checkout"), None),
        ],
    }
    return render(request, "orders/checkout.html", ctx)


def order_detail(request, ref):
    """Post-payment page: status, QR code and install instructions."""
    order = get_object_or_404(Order.objects.select_related("plan"), ref=ref)
    if not _can_view_order(request, order):
        raise Http404
    _settle_on_return(request, order)
    esim = order.esims.first() or order.target_esim
    events = []
    if order.status == Order.Status.COMPLETED and not order.analytics_sent:
        events.append(analytics.purchase(order))
        # Flip the flag in the same request that emits the event, so a refresh,
        # a shared link or a second tab never reports the sale again.
        Order.objects.filter(pk=order.pk, analytics_sent=False).update(analytics_sent=True)

    ctx = {
        "order": order,
        "esim": esim,
        "analytics_events": events,
        "seo_title": f"Order {order.ref} — {settings.SITE_NAME}",
        "meta_robots": "noindex,nofollow",
        # The page polls while the provider provisions (usually a second or two).
        "poll": order.status in (Order.Status.PENDING, Order.Status.PAID),
    }
    return render(request, "orders/order_detail.html", ctx)


def _settle_on_return(request, order):
    """Settle a card order from Stripe's return redirect if the webhook has not
    landed yet.

    The webhook is the primary path, but it can be late, misconfigured, or its
    signing secret simply unset -- and in every one of those cases the customer
    has paid and would otherwise sit on a spinner for ever. We do not trust the
    query string: it only tells us which session to go and ask Stripe about."""
    session_id = request.GET.get("session_id") or ""
    if order.status != Order.Status.PENDING or not session_id.startswith("cs_"):
        return
    from apps.payments import stripe_client
    from apps.payments import services as payment_services

    try:
        session = stripe_client.retrieve_session(session_id)
    except Exception:  # noqa: BLE001
        log.warning("could not read Stripe session %s for order %s", session_id, order.ref)
        return
    if str(session.get("client_reference_id") or "") not in {
        str(p.id) for p in order.payments.all()
    }:
        # The session belongs to a different order; never settle on it.
        return
    if session.get("payment_status") not in ("paid", "no_payment_required"):
        return
    try:
        payment_services.settle_stripe_session(session)
        order.refresh_from_db()
    except Exception:  # noqa: BLE001
        log.exception("return-page settlement failed for %s", order.ref)


def order_status_api(request, ref):
    order = get_object_or_404(Order, ref=ref)
    if not _can_view_order(request, order):
        raise Http404
    esim = order.esims.first() or order.target_esim
    return JsonResponse({
        "status": order.status,
        "ready": order.status == Order.Status.COMPLETED and esim is not None,
        "esim_url": esim.get_absolute_url() if esim and request.user.is_authenticated else "",
        "reload": order.status == Order.Status.COMPLETED,
    })


def qr_png(request, pk):
    """Render the LPA activation string as a QR code PNG."""
    esim = get_object_or_404(Esim, pk=pk)
    allowed = (
        (request.user.is_authenticated and esim.user_id == request.user.id)
        or request.user.is_staff
        or (esim.order and esim.order.ref in request.session.get(SESSION_ORDERS, []))
    )
    if not allowed:
        raise Http404
    if not esim.lpa_code:
        raise Http404

    import qrcode

    img = qrcode.make(esim.lpa_code, box_size=10, border=2)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    resp = HttpResponse(buf.getvalue(), content_type="image/png")
    resp["Cache-Control"] = "private, max-age=86400"
    resp["Content-Disposition"] = f'inline; filename="esim-{esim.iccid}.png"'
    return resp


@login_required
def dashboard(request):
    esims = list(request.user.esims.filter(is_deleted=False))
    active = [e for e in esims if e.is_active]
    inactive = [e for e in esims if not e.is_active]
    orders = request.user.orders.all()[:10]
    return render(request, "dashboard/index.html", {
        "active_esims": active,
        "inactive_esims": inactive,
        "orders": orders,
        "seo_title": f"My eSIMs — {settings.SITE_NAME}",
        "meta_robots": "noindex,nofollow",
    })


@login_required
def esim_detail(request, pk):
    esim = get_object_or_404(Esim, pk=pk, user=request.user)
    # Refresh usage on open, but never let a provider hiccup break the page.
    try:
        sync_esim(esim)
    except YesimError as e:
        log.warning("sim_info refresh failed for %s: %s", esim.iccid, e)
    topup_plans = []
    if esim.order and esim.order.plan:
        target = esim.order.plan.target
        if target:
            topup_plans = list(target.plans.live().order_by("price_usd")[:6])
    return render(request, "dashboard/esim_detail.html", {
        "esim": esim,
        "topup_plans": topup_plans,
        "seo_title": f"{esim.display_name} — {settings.SITE_NAME}",
        "meta_robots": "noindex,nofollow",
    })


@login_required
@require_POST
def esim_rename(request, pk):
    esim = get_object_or_404(Esim, pk=pk, user=request.user)
    esim.label = (request.POST.get("label") or "")[:80]
    esim.save(update_fields=["label"])
    messages.success(request, "Name updated.")
    return redirect(esim.get_absolute_url())


@login_required
def orders_list(request):
    return render(request, "dashboard/orders.html", {
        "orders": request.user.orders.select_related("plan").all(),
        "seo_title": f"Orders — {settings.SITE_NAME}",
        "meta_robots": "noindex,nofollow",
    })


@login_required
def topup(request, pk):
    """Pick a new plan for an eSIM the customer already owns."""
    esim = get_object_or_404(Esim, pk=pk, user=request.user)
    target = None
    if esim.order and esim.order.plan:
        target = esim.order.plan.target
    plans = list(target.plans.live()) if target else []
    data_plans = sorted([p for p in plans if not p.is_unlimited], key=lambda p: (p.days, p.data_gb or 0))
    unlimited = sorted([p for p in plans if p.is_unlimited], key=lambda p: p.days)
    return render(request, "dashboard/topup.html", {
        "esim": esim,
        "target": target,
        "data_plans": data_plans,
        "unlimited_plans": unlimited,
        "seo_title": f"Top up {esim.display_name}",
        "meta_robots": "noindex,nofollow",
    })
