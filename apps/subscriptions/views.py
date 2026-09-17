"""Customer-facing subscription flow: confirm, checkout, manage."""
from __future__ import annotations

import logging
from datetime import timedelta

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext as _
from django.views.decorators.http import require_POST

from apps.catalog.models import Plan
from apps.common import analytics
from apps.legal.models import LegalAcceptance, record_acceptance
from core.ratelimit import rate_limit

from . import stripe_sub
from .models import Subscription
from apps.subscriptions.catalogue import is_subscribable
from .services import resolve_esim, saving_pct, subscription_price

log = logging.getLogger(__name__)

# How long an abandoned Checkout attempt stays reusable. Stripe sessions expire
# after 24 hours; six is comfortably inside that and covers the customer who
# bounces off the payment page and comes back the same evening.
INCOMPLETE_REUSE_WINDOW = timedelta(hours=6)


def _enabled() -> bool:
    return bool(getattr(settings, "SUBSCRIPTIONS_ENABLED", True)) and stripe_sub.configured()


def _abs(request, path: str) -> str:
    return request.build_absolute_uri(path) if request is not None else f"{settings.SITE_URL}{path}"


def _pending_subscription(user, plan, price):
    """Reuse this customer's own abandoned attempt at this plan, or start one.

    Every abandonment at Stripe used to leave a row behind for ever. Reusing one
    keeps a customer who tries three times to one row, and the row still carries
    the reference the webhook looks for, so whichever Checkout session they
    eventually pay lands on it. Rows that already reached Stripe are never
    reused: that one has a subscription of its own waiting on a first payment.
    """
    recent = (Subscription.objects
              .filter(user=user, plan=plan, status=Subscription.Status.INCOMPLETE,
                      stripe_subscription_id__isnull=True,
                      created_at__gte=timezone.now() - INCOMPLETE_REUSE_WINDOW)
              .order_by("-created_at").first())
    if recent is None:
        return Subscription.objects.create(
            user=user, plan=plan, price_usd=price, interval_days=plan.days,
            status=Subscription.Status.INCOMPLETE,
        )
    # The catalogue may have moved since the attempt was abandoned.
    recent.price_usd = price
    recent.interval_days = plan.days
    recent.last_error = ""
    recent.save(update_fields=["price_usd", "interval_days", "last_error", "updated_at"])
    return recent


@login_required
@rate_limit("subscribe", 6, 3600)
def subscribe(request, plan_id):
    """Confirm on GET, create the Stripe Checkout session on POST.

    The confirmation step exists so the rate limit guards the expensive half:
    a GET costs us nothing, a POST creates a Subscription row and a Stripe
    session. It also gives us somewhere honest to show what recurs and when.
    """
    if not _enabled():
        raise Http404
    plan = get_object_or_404(
        Plan.objects.live().select_related("country", "region"), pk=plan_id,
    )
    # One definition of what may be subscribed to, checked here as well as in
    # the listing: a plan id in a URL is not a menu.
    if not is_subscribable(plan):
        raise Http404

    price = subscription_price(plan)
    error = ""

    # Never let one customer run two subscriptions for the same plan: that is
    # two charges and two eSIMs for one line they thought they were renewing.
    existing = (Subscription.objects
                .filter(user=request.user, plan=plan,
                        status__in=[Subscription.Status.ACTIVE,
                                    Subscription.Status.PAST_DUE,
                                    Subscription.Status.PAUSED])
                .first())
    if existing is not None:
        messages.info(request, _("You already have a subscription for this plan."))
        return redirect(existing.get_absolute_url())

    if request.method == "POST" and not request.POST.get("digital_consent"):
        # Same statutory waiver as one-off checkout: the first period is digital
        # content supplied at once, and an Estonian seller needs the buyer's
        # express request before delivering inside the withdrawal window.
        error = _("Please confirm you want the first period delivered immediately.")
    elif request.method == "POST":
        sub = _pending_subscription(request.user, plan, price)
        success_url = _abs(request, reverse("subscription_detail", kwargs={"pk": sub.pk}))
        cancel_url = _abs(request, reverse("subscribe", kwargs={"plan_id": plan.pk}))
        try:
            price_id = stripe_sub.ensure_price(plan)
            session = stripe_sub.create_checkout_session(
                request.user, plan, success_url + "?started=1", cancel_url,
                subscription_id=sub.pk, price_id=price_id,
            )
        except stripe_sub.SubscriptionError as e:
            log.warning("subscription checkout failed for %s: %s", request.user.email, e)
            sub.last_error = str(e)[:2000]
            sub.save(update_fields=["last_error", "updated_at"])
            error = _("We could not open the subscription checkout. Please try again "
                      "in a moment or contact support.")
        else:
            sub.stripe_price_id = price_id
            sub.save(update_fields=["stripe_price_id", "updated_at"])
            record_acceptance(request, user=request.user, email=request.user.email,
                              context=LegalAcceptance.Context.SUBSCRIBE)
            url = session.get("url") or ""
            if url:
                return redirect(url)
            error = _("Stripe did not return a checkout page. Please try again.")

    target = plan.target
    ctx = {
        "plan": plan,
        "target": target,
        "sub_price": price,
        "saving_pct": saving_pct(plan),
        "error": error,
        # Reported as begin_checkout so subscriptions and one-off sales share one
        # funnel; the recurring nature rides along in item_variant.
        "analytics_events": [analytics.subscribe_start(plan, price)],
        "seo_title": _("Subscribe — %(plan)s") % {"plan": plan.title},
        "meta_robots": "noindex,nofollow",
        "breadcrumbs": [
            (_("Home"), "/"),
            (plan.target_name, target.get_absolute_url() if target else "/"),
            (_("Subscribe"), None),
        ],
    }
    return render(request, "subscriptions/subscribe_intro.html", ctx)


@login_required
def subscriptions_list(request):
    subs = (Subscription.objects
            .filter(user=request.user)
            .select_related("plan", "plan__country", "plan__region", "esim")
            .exclude(status=Subscription.Status.INCOMPLETE))
    return render(request, "subscriptions/list.html", {
        "subscriptions": subs,
        "seo_title": _("Subscriptions — %(site)s") % {"site": settings.SITE_NAME},
        "meta_robots": "noindex,nofollow",
    })


@login_required
def subscription_detail(request, pk):
    sub = get_object_or_404(
        Subscription.objects.select_related("plan", "plan__country", "plan__region",
                                            "esim", "user"),
        pk=pk, user=request.user,
    )
    # A first cycle that failed at the provider and was retried from the orders
    # admin leaves the line unbound here; read it back so the customer sees the
    # eSIM they are paying for instead of "no eSIM issued yet".
    resolve_esim(sub)
    cycles = sub.cycles.select_related("order").all()[:24]
    return render(request, "subscriptions/detail.html", {
        "sub": sub,
        "cycles": cycles,
        # Straight after Stripe Checkout the webhook may still be in flight, so
        # the page says "setting up" instead of pretending something is wrong.
        "just_started": request.GET.get("started") == "1",
        "seo_title": _("Subscription — %(plan)s") % {"plan": sub.title},
        "meta_robots": "noindex,nofollow",
    })


@login_required
@require_POST
@rate_limit("billing_portal", 10, 3600)
def billing_portal(request):
    """Hand the customer to Stripe to update a card or cancel. Cancellation lives
    there on purpose: Stripe is the system of record for billing, and its portal
    handles proration, receipts and confirmation for us."""
    subs = Subscription.objects.filter(user=request.user).exclude(stripe_customer_id="")
    requested = request.POST.get("subscription")
    sub = None
    if requested:
        try:
            sub = subs.filter(pk=requested).first()
        except (ValidationError, ValueError):
            sub = None
    if sub is None:
        sub = subs.order_by("-created_at").first()
    back = reverse("subscription_detail", kwargs={"pk": sub.pk}) if sub \
        else reverse("subscriptions_list")

    if sub is None:
        messages.error(request, _("There is no billing account to manage yet."))
        return redirect("subscriptions_list")
    try:
        url = stripe_sub.billing_portal_url(sub.stripe_customer_id, _abs(request, back))
    except stripe_sub.SubscriptionError as e:
        log.warning("billing portal unavailable for %s: %s", request.user.email, e)
        messages.error(request, _("The billing portal is unavailable right now. "
                                  "Contact support and we will sort it out for you."))
        return redirect(back)
    return redirect(url)
