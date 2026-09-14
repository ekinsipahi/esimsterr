"""JSON API for the mobile app (JWT auth).

Store-policy note: the app never takes payment in-app. `POST /checkout/` returns
a web URL that the app opens in the system browser, where the customer pays for a
physical connectivity service. Nothing here creates an in-app purchase flow.
"""
from __future__ import annotations

from decimal import Decimal

from django.conf import settings
from django.db.models import Q
from urllib.parse import quote

from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes, throttle_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework_simplejwt.tokens import RefreshToken

from apps.accounts.emails import send_welcome
from apps.accounts.referrals import apply_referral_code
from apps.accounts.verification import send_verification
from apps.accounts.views import _client_ip
from apps.accounts.google import GoogleAuthError, user_from_google_token
from apps.accounts.models import User
from apps.catalog.models import Country, Device, Plan, Region
from apps.coupons.services import CouponError, redeem, release, validate_coupon
from apps.legal.documents import (BY_SLUG, DOCUMENTS, contract_stamps,
                                  document_url, stamp)
from apps.legal.models import LegalAcceptance, record_acceptance
from apps.orders.models import Esim, Order
from apps.orders.services import sync_esim
from apps.providers.yesim import YesimError

from .serializers import (CountrySerializer, EsimSerializer, OrderSerializer,
                          PlanSerializer, RegionSerializer)
from .throttles import AuthAnonThrottle, CheckoutThrottle, DeviceLookupThrottle


def _tokens(user):
    refresh = RefreshToken.for_user(user)
    return {"access": str(refresh.access_token), "refresh": str(refresh)}


def legal_surface(request) -> str:
    """Which platform is asking.

    The app sends X-Client-Platform. Anything else is treated as web, so a
    forged header can only ever get you a *different* public document, never a
    private one.
    """
    from apps.legal.registry import ALL_SURFACES, WEB

    value = (request.headers.get("X-Client-Platform") or "").strip().lower()
    return value if value in ALL_SURFACES else WEB


# ---- auth -------------------------------------------------------------------
@api_view(["POST"])
@permission_classes([AllowAny])
@throttle_classes([AuthAnonThrottle])
def register(request):
    email = (request.data.get("email") or "").strip().lower()
    password = request.data.get("password") or ""
    if not email or len(password) < 8:
        return Response({"detail": "Email and a password of at least 8 characters are required."},
                        status=status.HTTP_400_BAD_REQUEST)
    if User.objects.filter(email__iexact=email).exists():
        return Response({"detail": "An account with this email already exists."},
                        status=status.HTTP_400_BAD_REQUEST)
    user = User.objects.create_user(email=email, password=password)
    apply_referral_code(user, request.data.get("referral_code"))
    record_acceptance(request, user=user, email=user.email,
                      context=LegalAcceptance.Context.SIGNUP,
                      surface=legal_surface(request))
    # No tokens yet. The address is unproven, and handing out a session for an
    # account somebody may have opened in another person's name is exactly what
    # verification exists to stop. The welcome email waits until they confirm.
    send_verification(user, request)
    return Response({
        "user": {"email": user.email},
        "verification_required": True,
        "detail": "Check your inbox and open the link we sent to finish setting up.",
    }, status=201)



@api_view(["POST"])
@permission_classes([AllowAny])
@throttle_classes([AuthAnonThrottle])
def login(request):
    from django.contrib.auth import authenticate

    email = (request.data.get("email") or "").strip().lower()
    user = authenticate(request, username=email, password=request.data.get("password") or "")
    if user is None:
        return Response({"detail": "Incorrect email or password."}, status=400)
    if not user.email_verified:
        return Response({
            "detail": "Confirm your email address first. Check your inbox for the link.",
            "code": "email_unverified",
        }, status=status.HTTP_403_FORBIDDEN)
    return Response({"user": {"email": user.email}, **_tokens(user)})



@api_view(["POST"])
@permission_classes([AllowAny])
@throttle_classes([AuthAnonThrottle])
def google_login(request):
    try:
        user, created = user_from_google_token(request.data.get("id_token") or "")
    except GoogleAuthError as e:
        return Response({"detail": str(e)}, status=400)
    if created:
        send_welcome(user)
    return Response({"user": {"email": user.email}, "created": created, **_tokens(user)})



@api_view(["GET", "PATCH"])
def me(request):
    u = request.user
    if request.method == "PATCH":
        # One switch governs offers in the inbox and offers by email, because a
        # customer who turns notifications off means both and would rightly be
        # annoyed to keep getting one of them.
        if "notifications" in request.data:
            u.marketing_opt_in = bool(request.data.get("notifications"))
            u.save(update_fields=["marketing_opt_in"])
        if "display_name" in request.data:
            u.display_name = (request.data.get("display_name") or "")[:80]
            u.save(update_fields=["display_name"])
    return Response({
        "email": u.email,
        "display_name": u.display_name,
        "esim_count": u.esims.filter(is_deleted=False).count(),
        "notifications": u.marketing_opt_in,
        "email_verified": u.email_verified,
        "referral_code": u.referral_code or "",
    })


# ---- catalogue (public) ------------------------------------------------------
@api_view(["GET"])
@permission_classes([AllowAny])
def countries(request):
    qs = Country.objects.filter(is_active=True)
    q = (request.GET.get("q") or "").strip()
    if q:
        qs = qs.filter(Q(name__icontains=q) | Q(iso2__iexact=q))
    if request.GET.get("popular") == "1":
        qs = qs.filter(is_popular=True)
    return Response(CountrySerializer(qs.order_by("-is_popular", "name"), many=True,
                                      context={"request": request}).data)


@api_view(["GET"])
@permission_classes([AllowAny])
def regions(request):
    return Response(RegionSerializer(Region.objects.filter(is_active=True), many=True).data)


@api_view(["GET"])
@permission_classes([AllowAny])
def plans(request):
    """Plans for one destination: ?country=it or ?region=europe (slugs)."""
    qs = Plan.objects.live().select_related("country", "region")
    country = request.GET.get("country")
    region = request.GET.get("region")
    if country:
        qs = qs.filter(Q(country__slug=country) | Q(country__iso2__iexact=country))
    elif region:
        qs = qs.filter(region__slug=region)
    else:
        return Response({"detail": "Pass ?country= or ?region=."}, status=400)
    if request.GET.get("unlimited") == "1":
        qs = qs.filter(is_unlimited=True)
    return Response(PlanSerializer(qs.order_by("is_unlimited", "days", "data_gb"), many=True).data)


@api_view(["GET"])
@permission_classes([AllowAny])
def devices(request):
    brands: dict[str, list[str]] = {}
    for d in Device.objects.all():
        brands.setdefault(d.brand, []).append(d.model)
    return Response([{"brand": b, "models": m} for b, m in sorted(brands.items())])


# ---- customer data -----------------------------------------------------------
@api_view(["GET"])
def my_esims(request):
    qs = request.user.esims.filter(is_deleted=False)
    return Response(EsimSerializer(qs, many=True).data)


@api_view(["GET"])
def esim_detail(request, pk):
    esim = request.user.esims.filter(pk=pk).first()
    if esim is None:
        return Response({"detail": "Not found."}, status=404)
    if request.GET.get("refresh") == "1":
        try:
            sync_esim(esim)
        except YesimError:
            pass
    return Response(EsimSerializer(esim).data)


@api_view(["PATCH"])
def esim_rename(request, pk):
    esim = request.user.esims.filter(pk=pk).first()
    if esim is None:
        return Response({"detail": "Not found."}, status=404)
    esim.label = (request.data.get("label") or "")[:80]
    esim.save(update_fields=["label"])
    return Response(EsimSerializer(esim).data)


@api_view(["GET"])
def my_orders(request):
    return Response(OrderSerializer(request.user.orders.all()[:50], many=True).data)


@api_view(["POST"])
@permission_classes([AllowAny])
@throttle_classes([CheckoutThrottle])
def checkout_url(request):
    """Return the WEB checkout URL for a plan — the app opens it in the system
    browser. Payment never happens inside the app (store-policy safe)."""
    plan = Plan.objects.live().filter(pk=request.data.get("plan_id")).first()
    if plan is None:
        return Response({"detail": "Plan not found."}, status=404)
    path = reverse("checkout", kwargs={"plan_id": plan.pk})
    params = []
    esim_id = request.data.get("esim_id")
    if esim_id and request.user.is_authenticated and \
            Esim.objects.filter(pk=esim_id, user=request.user).exists():
        params.append(f"esim={esim_id}")
    device_id = _support_id(request)
    if device_id:
        # Binds the resulting guest order to this installation, so the app can
        # show it afterwards without anyone having to register.
        params.append(f"device={device_id}")
    gift_email = (request.data.get("gift_email") or "").strip()
    if gift_email:
        # Carried through to the web checkout so the buyer sees, and confirms,
        # that the QR is going somewhere other than their own inbox.
        params.append(f"gift={quote(gift_email)}")
        gift_name = (request.data.get("gift_name") or "").strip()
        if gift_name:
            params.append(f"gift_name={quote(gift_name)}")
    if params:
        path = f"{path}?{'&'.join(params)}"
    return Response({
        "url": f"{settings.SITE_URL}{path}",
        "plan": PlanSerializer(plan).data,
        "open_in": "external_browser",
    })



@api_view(["GET"])
@permission_classes([AllowAny])
def config(request):
    from apps.payments.inapp import enabled as in_app_enabled

    """Bootstrap payload so the app can render without hardcoding anything."""
    return Response({
        "site_name": settings.SITE_NAME,
        "site_url": settings.SITE_URL,
        "support_email": settings.SUPPORT_EMAIL,
        "currency": "USD",
        "min_supported_version": "1.0.0",
        "country_count": Country.objects.filter(is_active=True).count(),
        # The app compares these against what the customer last accepted and
        # shows the changed document. Cheaper than a push, and it cannot be
        # missed by someone who has notifications switched off.
        "legal": contract_stamps(legal_surface(request)),
        # The app reads the publishable key from here rather than baking it in:
        # rotating a Stripe key should not need a store release.
        "in_app_payments": in_app_enabled(),
        "stripe_publishable_key": settings.STRIPE_PUBLISHABLE_KEY if in_app_enabled() else "",
    })


# ---- legal ------------------------------------------------------------------
@api_view(["GET"])
@permission_classes([AllowAny])
def legal_index(request):
    """The documents in force, with the version the app should show and record.

    The app renders these rather than bundling its own copy: a policy that ships
    inside a binary is one that cannot be corrected without a store review.
    """
    surface = legal_surface(request)
    return Response({
        "surface": surface,
        "documents": [
            {
                "slug": d.slug,
                "title": d.title,
                "summary": d.summary,
                "version": d.version,
                "effective": d.effective.isoformat(),
                "stamp": stamp(d, surface),
                "url": request.build_absolute_uri(document_url(d)),
            }
            for d in DOCUMENTS if d.applies_to(surface)
        ],
    })


@api_view(["GET"])
@permission_classes([AllowAny])
def legal_document(request, slug):
    """One document as structured blocks, composed for the calling platform."""
    from apps.legal.documents import render as render_doc

    doc = BY_SLUG.get(slug)
    surface = legal_surface(request)
    if doc is None or not doc.applies_to(surface):
        return Response({"detail": "No such document."}, status=status.HTTP_404_NOT_FOUND)
    return Response({
        "slug": doc.slug, "title": doc.title, "summary": doc.summary,
        "version": doc.version, "effective": doc.effective.isoformat(),
        "stamp": stamp(doc, surface), "surface": surface,
        "url": request.build_absolute_uri(document_url(doc)),
        "sections": [
            {"number": c.number, "id": c.slug, "title": c.title,
             "html": "".join(str(b.render()) for b in c.blocks)}
            for c in render_doc(doc, surface)
        ],
    })


@api_view(["POST"])
def legal_accept(request):
    """Record that the signed-in customer accepted the current documents.

    Called by the app after it shows a changed policy. Idempotent in practice:
    a second call writes a second row with the same stamp, which is a truthful
    record of them having seen it twice.
    """
    record_acceptance(request, user=request.user, email=request.user.email,
                      context=LegalAcceptance.Context.APP,
                      surface=legal_surface(request))
    return Response({"ok": True})


# ---- account ----------------------------------------------------------------
@api_view(["POST", "DELETE"])
def delete_account_api(request):
    """In-app account deletion.

    App Store guideline 5.1.1(v) requires an app that creates accounts to let you
    delete one from inside it -- not a link to a support email. The confirmation
    string is required for the same reason the web form requires it: this cancels
    billing and erases support history, and a mis-tap should not do that.
    """
    from apps.accounts.deletion import DeletionBlocked, delete_account

    confirm = (request.data.get("confirm") or "").strip().upper()
    if confirm != "DELETE":
        return Response({"detail": 'Send {"confirm": "DELETE"} to confirm.'},
                        status=status.HTTP_400_BAD_REQUEST)
    try:
        report = delete_account(request.user)
    except DeletionBlocked as e:
        return Response({"detail": str(e)}, status=status.HTTP_409_CONFLICT)
    return Response({"ok": True, "deleted": report.as_lines()})


# ---- wallet ------------------------------------------------------------------
def _wallet_payload(request, wallet):
    from apps.wallet.services import limits, presets

    low, high = limits()
    return {
        "balance_usd": str(wallet.balance_usd),
        "topped_up_usd": str(wallet.topped_up_usd),
        "spent_usd": str(wallet.spent_usd),
        "currency": "USD",
        "min_topup_usd": str(low),
        "max_topup_usd": str(high),
        "presets": [
            {"amount_usd": str(p["amount"]), "bonus_usd": str(p["bonus"]),
             "total_usd": str(p["total"]), "bonus_pct": p["bonus_pct"]}
            for p in presets()
        ],
        "transactions": [
            {"id": str(t.id), "kind": t.kind, "kind_label": t.get_kind_display(),
             "amount_usd": str(t.amount_usd), "balance_after_usd": str(t.balance_after_usd),
             "description": t.description, "is_credit": t.is_credit,
             "created_at": t.created_at.isoformat()}
            for t in wallet.transactions.all()[:50]
        ],
    }


@api_view(["GET"])
def wallet(request):
    from apps.wallet.models import Wallet

    return Response(_wallet_payload(request, Wallet.for_user(request.user)))


@api_view(["POST"])
def wallet_topup_url(request):
    """Return the WEB page where credit is bought.

    The app opens this in the system browser and never collects payment itself.
    That is the same rule that governs buying a plan, applied to buying credit:
    money moves on the website, the app only ever spends what is already there.
    """
    amount = request.data.get("amount")
    from apps.wallet.services import validate_amount

    try:
        amount = validate_amount(amount)
    except ValueError as e:
        return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)
    path = reverse("wallet_add")
    url = request.build_absolute_uri(
        f"{path}?amount={amount}&src={legal_surface(request)}"
    )
    return Response({"url": url, "amount_usd": str(amount)})


@api_view(["POST"])
@throttle_classes([CheckoutThrottle])
def pay_with_balance(request):
    """Buy a plan out of store credit, in the app, with no payment step.

    Nothing here talks to a payment processor: the customer already bought the
    credit on the website. Coupons still apply, because a discount on a plan is
    a discount whichever pocket the money comes from.
    """
    from apps.legal.models import LegalAcceptance, record_acceptance
    from apps.wallet.models import InsufficientBalance, Wallet
    from apps.wallet.services import pay_order_with_balance

    if not request.data.get("consent"):
        # The same statutory acknowledgement the web checkout collects. An app
        # that skipped it would deliver inside the withdrawal window without the
        # buyer's express request, which is the seller's problem, not theirs.
        return Response(
            {"detail": "Confirm immediate delivery to continue.",
             "code": "consent_required"},
            status=status.HTTP_400_BAD_REQUEST,
        )

    plan = Plan.objects.live().select_related("country", "region").filter(
        pk=request.data.get("plan_id")).first()
    if plan is None:
        return Response({"detail": "Plan not found."}, status=status.HTTP_404_NOT_FOUND)

    target_esim = None
    esim_id = request.data.get("esim_id")
    if esim_id:
        target_esim = request.user.esims.filter(pk=esim_id, is_deleted=False).first()
        if target_esim is None:
            return Response({"detail": "eSIM not found."}, status=status.HTTP_404_NOT_FOUND)

    subtotal = Decimal(plan.price)
    coupon, discount = None, Decimal("0.00")
    code = (request.data.get("coupon") or "").strip()
    if code:
        try:
            coupon, discount = validate_coupon(
                code, amount_usd=subtotal, plan=plan,
                user=request.user, email=request.user.email,
            )
        except CouponError as e:
            return Response({"detail": str(e), "code": "coupon_invalid"},
                            status=status.HTTP_400_BAD_REQUEST)

    total = (subtotal - discount).quantize(Decimal("0.01"))
    wallet_row = Wallet.for_user(request.user)
    if wallet_row.balance_usd < total:
        return Response(
            {"detail": "Not enough balance.", "code": "insufficient_balance",
             "balance_usd": str(wallet_row.balance_usd), "needed_usd": str(total)},
            status=status.HTTP_402_PAYMENT_REQUIRED,
        )

    order = Order.objects.create(
        user=request.user, email=request.user.email,
        kind=Order.Kind.TOPUP if target_esim else Order.Kind.NEW,
        plan=plan, plan_title=plan.title, plan_provider_id=plan.provider_plan_id,
        plan_days=plan.days, plan_data_label=plan.data_label,
        subtotal_usd=subtotal, discount_usd=discount, amount_usd=total,
        coupon=coupon, coupon_code=coupon.code if coupon else "",
        cost_amount=plan.cost_amount, cost_currency=plan.cost_currency,
        target_esim=target_esim, withdrawal_waived_at=timezone.now(),
        source=legal_surface(request), paid_with_balance=True,
        is_test=bool(request.user.is_test),
        support_id=(request.headers.get("X-Support-Id") or "")[:24],
        gift_email=(request.data.get("gift_email") or "").strip()[:254],
        gift_name=(request.data.get("gift_name") or "").strip()[:80],
        gift_message=(request.data.get("gift_message") or "").strip()[:300],
        ip=_client_ip(request),
        user_agent=(request.META.get("HTTP_USER_AGENT") or "")[:400],
    )
    if coupon is not None:
        try:
            redeem(coupon, order, user=request.user, email=request.user.email, ip=order.ip)
        except CouponError as e:
            order.coupon, order.coupon_code = None, ""
            order.discount_usd = Decimal("0.00")
            order.amount_usd = subtotal
            order.save(update_fields=["coupon", "coupon_code", "discount_usd", "amount_usd"])
            return Response({"detail": str(e), "code": "coupon_invalid"},
                            status=status.HTTP_400_BAD_REQUEST)

    try:
        pay_order_with_balance(request.user, order)
    except InsufficientBalance as e:
        # Someone spent the balance between the check above and here. Releasing
        # the coupon seat matters: a capped code must not be burned by an order
        # that never happened.
        from apps.coupons.services import release

        release(order)
        order.status = Order.Status.FAILED
        order.save(update_fields=["status"])
        return Response({"detail": str(e), "code": "insufficient_balance"},
                        status=status.HTTP_402_PAYMENT_REQUIRED)

    record_acceptance(request, user=request.user, email=request.user.email,
                      context=LegalAcceptance.Context.CHECKOUT,
                      order_ref=order.ref, surface=legal_surface(request))

    order.refresh_from_db()
    return Response({
        "order": OrderSerializer(order).data,
        "wallet": _wallet_payload(request, Wallet.for_user(request.user)),
    }, status=201)


# ---- inbox -------------------------------------------------------------------
def _message_json(message, read_ids: set) -> dict:
    return {
        "id": message.id,
        "title": message.title,
        "body": message.body,
        "kind": message.kind,
        "kind_label": message.get_kind_display(),
        "cta_label": message.cta_label,
        "cta_url": message.absolute_cta(),
        "coupon_code": message.coupon_code,
        "published_at": message.publish_at.isoformat(),
        "expires_at": message.expires_at.isoformat() if message.expires_at else None,
        "read": message.id in read_ids,
    }


@api_view(["GET"])
def inbox(request):
    """Messages this customer may see, newest first, with the unread count.

    Marketing consent is applied inside `for_user`, so a campaign written by
    somebody who forgot about opt-outs still cannot reach a customer who opted
    out."""
    from apps.inbox.models import InboxMessage, InboxRead

    messages = list(InboxMessage.for_user(request.user)[:60])
    read_ids = set(
        InboxRead.objects.filter(user=request.user, message__in=messages)
        .values_list("message_id", flat=True)
    )
    return Response({
        "unread": sum(1 for m in messages if m.id not in read_ids),
        "messages": [_message_json(m, read_ids) for m in messages],
    })


@api_view(["POST"])
def inbox_read(request, pk):
    from apps.inbox.models import InboxMessage, InboxRead

    message = InboxMessage.for_user(request.user).filter(pk=pk).first()
    if message is None:
        return Response({"detail": "No such message."}, status=status.HTTP_404_NOT_FOUND)
    InboxRead.objects.get_or_create(user=request.user, message=message)
    return Response({"ok": True})


@api_view(["POST"])
def inbox_read_all(request):
    from apps.inbox.models import InboxMessage, InboxRead

    messages = InboxMessage.for_user(request.user)
    InboxRead.objects.bulk_create(
        [InboxRead(user=request.user, message=m) for m in messages],
        ignore_conflicts=True,
    )
    return Response({"ok": True})


# ---- referrals ---------------------------------------------------------------
@api_view(["GET"])
def referral(request):
    from apps.wallet.services import referral_progress

    progress = referral_progress(request.user)
    code = progress["code"]
    link = f"{settings.SITE_URL.rstrip('/')}/signup/?ref={code}" if code else ""
    return Response({
        **{k: (str(v) if hasattr(v, "quantize") else v) for k, v in progress.items()},
        "link": link,
        "share_text": (
            f"I use {settings.SITE_NAME} for travel data — no roaming bills. "
            f"Use my code {code} when you sign up: {link}" if code else ""
        ),
    })


@api_view(["POST"])
def referral_apply(request):
    """Enter a code after the fact.

    Allowed only while the account is new and has bought nothing: a code applied
    after a customer is already established is not a referral, it is somebody
    claiming credit for a customer they did not bring."""
    from apps.accounts.referrals import ReferralError, apply_referral_code

    try:
        referrer = apply_referral_code(request.user, request.data.get("code"), strict=True)
    except ReferralError as e:
        return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)
    return Response({"ok": True, "referred_by": referrer.email})


# ---- device-bound guest purchases --------------------------------------------
def _attestation_gate(support_id: str):
    """None to proceed, or a Response refusing an unattested device.

    Only bites once Play Integrity is configured *and* switched to required.
    Before that an unattested device is the only kind there is, and refusing
    them all would mean nobody could see what they bought.
    """
    from apps.accounts.integrity import required
    from apps.accounts.models import AppInstall

    if not required():
        return None
    install = AppInstall.objects.filter(support_id=support_id).first()
    if install is not None and install.is_attested:
        return None
    return Response(
        {"detail": "This device has not been verified with Google Play.",
         "code": "attestation_required"},
        status=status.HTTP_403_FORBIDDEN,
    )


def _support_id(request) -> str:
    """The calling installation's code, or "" if it is missing or malformed."""
    from apps.accounts.install_middleware import SUPPORT_ID

    value = (request.headers.get("X-Support-Id") or "").strip().upper()
    return value if SUPPORT_ID.match(value) else ""


@api_view(["GET"])
@permission_classes([AllowAny])
@throttle_classes([DeviceLookupThrottle])
def device_esims(request):
    """The eSIMs bought from this device without an account.

    Buying should not require registering. The support ID is the identity: the
    order was placed from this installation, so this installation can see it.
    Once an order belongs to a signed-up customer it is account-protected and
    disappears from here, because an account is a stronger claim than a device.

    The ID is 8 characters from a 32-letter alphabet -- about 10^12 -- and this
    endpoint is throttled, so guessing one is not a route in. It is still only a
    bearer secret, which is exactly why it buys nothing and changes nothing: it
    only reads back what this device already paid for.
    """
    support_id = _support_id(request)
    if not support_id:
        return Response({"detail": "No device id."}, status=status.HTTP_400_BAD_REQUEST)

    gate = _attestation_gate(support_id)
    if gate is not None:
        return gate

    orders = Order.objects.filter(support_id=support_id, user__isnull=True)
    esims = (Esim.objects.filter(order__in=orders, is_deleted=False)
             .order_by("-created_at"))
    return Response({
        "device_id": support_id,
        "esims": EsimSerializer(esims, many=True).data,
        "orders": OrderSerializer(orders.order_by("-created_at")[:50], many=True).data,
    })


@api_view(["POST"])
def device_claim(request):
    """Attach this device's guest purchases to the account that just signed in.

    Somebody who bought as a guest and later registers should not have to email
    support to see what they already own. Only unclaimed orders move, and only
    ones placed from the installation making the request."""
    support_id = _support_id(request)
    if not support_id:
        return Response({"detail": "No device id."}, status=status.HTTP_400_BAD_REQUEST)

    orders = Order.objects.filter(support_id=support_id, user__isnull=True)
    esim_ids = list(Esim.objects.filter(order__in=orders, user__isnull=True)
                    .values_list("pk", flat=True))
    moved = orders.update(user=request.user)
    Esim.objects.filter(pk__in=esim_ids).update(user=request.user)

    # Carry the saved cards over too. A guest who saved a card and then
    # registered should not have to type it again -- and leaving the customer on
    # the device row would strand the card somewhere nothing reads.
    from apps.accounts.models import AppInstall

    install = AppInstall.objects.filter(support_id=support_id).first()
    if install and install.stripe_customer_id and not request.user.stripe_customer_id:
        request.user.stripe_customer_id = install.stripe_customer_id
        request.user.save(update_fields=["stripe_customer_id"])
        install.stripe_customer_id = ""
        install.save(update_fields=["stripe_customer_id"])

    return Response({"ok": True, "orders_claimed": moved, "esims_claimed": len(esim_ids)})


@api_view(["POST"])
@permission_classes([AllowAny])
@throttle_classes([AuthAnonThrottle])
def resend_verification(request):
    """Send the confirmation link again.

    The answer never reveals whether the address has an account: otherwise this
    becomes a way to test which emails are registered.
    """
    email = (request.data.get("email") or "").strip().lower()
    if email:
        user = User.objects.filter(email__iexact=email, email_verified=False).first()
        if user is not None:
            send_verification(user, request)
    return Response({"ok": True,
                     "detail": "If that address needs confirming, the link is on its way."})


@api_view(["GET"])
@permission_classes([AllowAny])
@throttle_classes([DeviceLookupThrottle])
def device_nonce(request):
    """A one-shot value the app binds its Play Integrity verdict to.

    Without it a verdict captured once could be replayed for ever, which would
    make attestation a slightly longer bearer secret rather than a proof.
    """
    from apps.accounts.integrity import configured, issue_nonce

    support_id = _support_id(request)
    if not support_id:
        return Response({"detail": "No device id."}, status=status.HTTP_400_BAD_REQUEST)
    if not configured():
        return Response({"enabled": False, "nonce": ""})
    return Response({"enabled": True, "nonce": issue_nonce(support_id)})


@api_view(["POST"])
@permission_classes([AllowAny])
@throttle_classes([DeviceLookupThrottle])
def device_attest(request):
    """Hand back a Play Integrity token; we ask Google what it says."""
    from apps.accounts.integrity import attest, configured
    from apps.accounts.models import AppInstall

    support_id = _support_id(request)
    if not support_id:
        return Response({"detail": "No device id."}, status=status.HTTP_400_BAD_REQUEST)
    if not configured():
        return Response({"enabled": False, "verified": False,
                         "detail": "Play Integrity is not configured on the server."})

    token = (request.data.get("token") or "").strip()
    if not token:
        return Response({"detail": "No integrity token."}, status=status.HTTP_400_BAD_REQUEST)

    install, _created = AppInstall.objects.get_or_create(
        support_id=support_id,
        defaults={"platform": (request.headers.get("X-Client-Platform") or "android")[:12]},
    )
    ok, reason = attest(install, token)
    return Response({"enabled": True, "verified": ok, "detail": reason},
                    status=status.HTTP_200_OK if ok else status.HTTP_403_FORBIDDEN)


# ---- paying with a card, inside the app --------------------------------------
def _build_order(request, *, plan, email: str, paid_with_balance: bool):
    """Create a pending order from the request, or return (None, error Response).

    Shared by both in-app payment routes so a coupon, a gift or a top-up target
    behaves identically whether the money comes from a card or from balance.
    """
    user = request.user if request.user.is_authenticated else None

    target_esim = None
    esim_id = request.data.get("esim_id")
    if esim_id:
        owned = Esim.objects.filter(pk=esim_id, is_deleted=False)
        target_esim = owned.filter(user=user).first() if user else None
        if target_esim is None:
            return None, Response({"detail": "eSIM not found."},
                                  status=status.HTTP_404_NOT_FOUND)

    subtotal = Decimal(plan.price)
    coupon, discount = None, Decimal("0.00")
    code = (request.data.get("coupon") or "").strip()
    if code:
        try:
            coupon, discount = validate_coupon(
                code, amount_usd=subtotal, plan=plan, user=user, email=email,
            )
        except CouponError as e:
            return None, Response({"detail": str(e), "code": "coupon_invalid"},
                                  status=status.HTTP_400_BAD_REQUEST)

    order = Order.objects.create(
        user=user, email=email,
        kind=Order.Kind.TOPUP if target_esim else Order.Kind.NEW,
        plan=plan, plan_title=plan.title, plan_provider_id=plan.provider_plan_id,
        plan_days=plan.days, plan_data_label=plan.data_label,
        subtotal_usd=subtotal, discount_usd=discount,
        amount_usd=(subtotal - discount).quantize(Decimal("0.01")),
        coupon=coupon, coupon_code=coupon.code if coupon else "",
        cost_amount=plan.cost_amount, cost_currency=plan.cost_currency,
        target_esim=target_esim, withdrawal_waived_at=timezone.now(),
        source=legal_surface(request), paid_with_balance=paid_with_balance,
        support_id=_support_id(request),
        is_test=bool(user is not None and user.is_test),
        gift_email=(request.data.get("gift_email") or "").strip()[:254],
        gift_name=(request.data.get("gift_name") or "").strip()[:80],
        gift_message=(request.data.get("gift_message") or "").strip()[:300],
        ip=_client_ip(request),
        user_agent=(request.META.get("HTTP_USER_AGENT") or "")[:400],
    )
    if coupon is not None:
        try:
            redeem(coupon, order, user=user, email=email, ip=order.ip)
        except CouponError as e:
            order.coupon, order.coupon_code = None, ""
            order.discount_usd = Decimal("0.00")
            order.amount_usd = subtotal
            order.save(update_fields=["coupon", "coupon_code", "discount_usd", "amount_usd"])
            return None, Response({"detail": str(e), "code": "coupon_invalid"},
                                  status=status.HTTP_400_BAD_REQUEST)
    return order, None


@api_view(["POST"])
@permission_classes([AllowAny])
@throttle_classes([CheckoutThrottle])
def payment_sheet(request):
    """Start an in-app card payment.

    Returns what Stripe's PaymentSheet needs and nothing else. Card details go
    from the device to Stripe directly and never reach this server -- what comes
    back afterwards is a payment method id, which cannot charge anything
    anywhere else.

    Works signed out. The customer is keyed to the device install then, so a
    guest who saves a card gets it back next time, which is the only thing that
    makes saving one worth doing.
    """
    from apps.accounts.models import AppInstall
    from apps.legal.models import LegalAcceptance, record_acceptance
    from apps.payments.inapp import InAppError, customer_for, enabled, payment_sheet as build_sheet
    from apps.payments.stripe_client import StripeError

    if not enabled():
        return Response({"detail": "In-app payments are unavailable.",
                         "code": "in_app_unavailable"},
                        status=status.HTTP_503_SERVICE_UNAVAILABLE)

    if not request.data.get("consent"):
        return Response({"detail": "Confirm immediate delivery to continue.",
                         "code": "consent_required"},
                        status=status.HTTP_400_BAD_REQUEST)

    plan = Plan.objects.live().select_related("country", "region").filter(
        pk=request.data.get("plan_id")).first()
    if plan is None:
        return Response({"detail": "Plan not found."}, status=status.HTTP_404_NOT_FOUND)

    # A guest has to give us somewhere to send the eSIM.
    email = (request.data.get("email") or "").strip().lower()
    if request.user.is_authenticated:
        email = request.user.email
    elif not email or "@" not in email:
        return Response({"detail": "Enter an email address so we can send the eSIM.",
                         "code": "email_required"},
                        status=status.HTTP_400_BAD_REQUEST)

    install = None
    if not request.user.is_authenticated:
        support_id = _support_id(request)
        if not support_id:
            return Response({"detail": "No device id."}, status=status.HTTP_400_BAD_REQUEST)
        install, _ = AppInstall.objects.get_or_create(
            support_id=support_id,
            defaults={"platform": (request.headers.get("X-Client-Platform") or "android")[:12]},
        )

    order, error = _build_order(request, plan=plan, email=email, paid_with_balance=False)
    if error is not None:
        return error

    try:
        customer_id, _owner = customer_for(
            user=request.user if request.user.is_authenticated else None,
            install=install, email=email,
        )
        sheet = build_sheet(
            order,
            customer_id=customer_id,
            api_version=(request.data.get("stripe_version") or "2024-06-20"),
            save_card=bool(request.data.get("save_card", True)),
        )
    except (InAppError, StripeError) as e:
        release(order)
        order.status = Order.Status.FAILED
        order.save(update_fields=["status"])
        return Response({"detail": str(e)}, status=status.HTTP_502_BAD_GATEWAY)

    record_acceptance(request, user=request.user if request.user.is_authenticated else None,
                      email=email, context=LegalAcceptance.Context.CHECKOUT,
                      order_ref=order.ref, surface=legal_surface(request))
    return Response(sheet, status=201)


@api_view(["GET"])
@permission_classes([AllowAny])
@throttle_classes([DeviceLookupThrottle])
def saved_cards(request):
    """The cards this customer, or this device, has saved."""
    from apps.accounts.models import AppInstall
    from apps.payments.inapp import enabled
    from apps.payments.stripe_client import list_cards

    if not enabled():
        return Response({"cards": []})

    if request.user.is_authenticated:
        customer_id = request.user.stripe_customer_id
    else:
        support_id = _support_id(request)
        install = AppInstall.objects.filter(support_id=support_id).first() if support_id else None
        customer_id = install.stripe_customer_id if install else ""
    return Response({"cards": list_cards(customer_id)})


@api_view(["DELETE", "POST"])
@permission_classes([AllowAny])
@throttle_classes([DeviceLookupThrottle])
def delete_card(request, pm_id):
    """Forget a card. Refuses unless it belongs to the caller's own customer."""
    from apps.accounts.models import AppInstall
    from apps.payments.stripe_client import StripeError, card_belongs_to, detach_card

    if request.user.is_authenticated:
        customer_id = request.user.stripe_customer_id
    else:
        support_id = _support_id(request)
        install = AppInstall.objects.filter(support_id=support_id).first() if support_id else None
        customer_id = install.stripe_customer_id if install else ""

    if not card_belongs_to(pm_id, customer_id):
        return Response({"detail": "No such card."}, status=status.HTTP_404_NOT_FOUND)
    try:
        detach_card(pm_id)
    except StripeError as e:
        return Response({"detail": str(e)}, status=status.HTTP_502_BAD_GATEWAY)
    return Response({"ok": True})


# ---- admin test tool ---------------------------------------------------------
@api_view(["POST"])
@permission_classes([AllowAny])
def dev_grant_balance(request):
    """Put credit in an account without anyone paying for it.

    This is the whole bypass. Everything downstream -- buying, coupons,
    provisioning -- then runs as it does for a real customer, which is the only
    way a test tells you anything about the real thing.
    """
    from apps.accounts.models import User
    from apps.api import devtools
    from apps.wallet.models import Wallet, WalletTransaction

    if not devtools.authorised(request):
        return Response({"detail": "Not available."}, status=status.HTTP_404_NOT_FOUND)

    email = (request.data.get("email") or "").strip().lower()
    user = (request.user if request.user.is_authenticated
            else User.objects.filter(email__iexact=email).first())
    if user is None:
        return Response({"detail": "No such account."}, status=status.HTTP_404_NOT_FOUND)

    try:
        amount = Decimal(str(request.data.get("amount") or "25"))
    except Exception:  # noqa: BLE001
        return Response({"detail": "Bad amount."}, status=status.HTTP_400_BAD_REQUEST)
    if amount <= 0 or amount > Decimal("1000"):
        return Response({"detail": "Amount must be between 0 and 1000."},
                        status=status.HTTP_400_BAD_REQUEST)

    Wallet.credit(user, amount, kind=WalletTransaction.Kind.ADJUST,
                  description="Admin test credit — not paid for")
    if not user.is_test:
        # Holding money nobody paid for makes this a test account, and every
        # order it places from here on is excluded from revenue and alerts.
        user.is_test = True
        user.save(update_fields=["is_test"])
    devtools.note("granted balance", email=user.email, amount=amount,
                  marked_test=True)
    wallet = Wallet.for_user(user)
    return Response({"ok": True, "email": user.email,
                     "balance_usd": str(wallet.balance_usd)})


@api_view(["POST"])
@permission_classes([AllowAny])
def dev_complete_order(request):
    """Create an order and settle it without payment, then provision for real.

    Takes the same fields the real purchase does -- plan, coupon, gift, device --
    and runs them through the same order builder, so a coupon that would be
    refused in production is refused here too.
    """
    from apps.api import devtools
    from apps.accounts.models import AppInstall
    from apps.legal.models import LegalAcceptance, record_acceptance

    if not devtools.authorised(request):
        return Response({"detail": "Not available."}, status=status.HTTP_404_NOT_FOUND)

    plan = Plan.objects.live().select_related("country", "region").filter(
        pk=request.data.get("plan_id")).first()
    if plan is None:
        return Response({"detail": "Plan not found."}, status=status.HTTP_404_NOT_FOUND)

    email = (request.data.get("email") or "").strip().lower()
    if request.user.is_authenticated:
        email = request.user.email
    if not email or "@" not in email:
        return Response({"detail": "An email is required, even for a test."},
                        status=status.HTTP_400_BAD_REQUEST)

    support_id = _support_id(request)
    if support_id and not request.user.is_authenticated:
        AppInstall.objects.get_or_create(
            support_id=support_id,
            defaults={"platform": (request.headers.get("X-Client-Platform") or "android")[:12]},
        )

    order, error = _build_order(request, plan=plan, email=email, paid_with_balance=False)
    if error is not None:
        return error

    order.is_test = True
    order.save(update_fields=["is_test"])
    order.mark_paid()
    record_acceptance(request, user=request.user if request.user.is_authenticated else None,
                      email=email, context=LegalAcceptance.Context.CHECKOUT,
                      order_ref=order.ref, surface=legal_surface(request))
    devtools.note("completed order without payment", ref=order.ref, email=email,
                  plan=plan.title, amount=order.amount_usd, device=support_id or "-")

    provisioned, detail = False, "skipped"
    if request.data.get("provision", True):
        from apps.orders.services import fulfill_order

        try:
            fulfill_order(order.pk)
            order.refresh_from_db()
            provisioned, detail = order.status == Order.Status.COMPLETED, order.fulfillment_error or "ok"
        except Exception as e:  # noqa: BLE001
            detail = str(e)[:300]

    order.refresh_from_db()
    esim = Esim.objects.filter(order=order).first()
    return Response({
        "ok": True,
        "order": OrderSerializer(order).data,
        "provisioned": provisioned,
        "detail": detail,
        "esim": EsimSerializer(esim).data if esim else None,
    }, status=201)


@api_view(["GET"])
@permission_classes([AllowAny])
def dev_status(request):
    """Whether the tool is switched on, and what this caller looks like to it."""
    from apps.api import devtools

    if not devtools.authorised(request):
        return Response({"enabled": False}, status=status.HTTP_404_NOT_FOUND)
    return Response({
        "enabled": True,
        "signed_in": request.user.is_authenticated,
        "email": request.user.email if request.user.is_authenticated else "",
        "device_id": _support_id(request),
        "surface": legal_surface(request),
    })
