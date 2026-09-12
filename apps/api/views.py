"""JSON API for the mobile app (JWT auth).

Store-policy note: the app never takes payment in-app. `POST /checkout/` returns
a web URL that the app opens in the system browser, where the customer pays for a
physical connectivity service. Nothing here creates an in-app purchase flow.
"""
from __future__ import annotations

from django.conf import settings
from django.db.models import Q
from django.urls import reverse
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes, throttle_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework_simplejwt.tokens import RefreshToken

from apps.accounts.emails import send_welcome
from apps.accounts.google import GoogleAuthError, user_from_google_token
from apps.accounts.models import User
from apps.catalog.models import Country, Device, Plan, Region
from apps.orders.models import Esim, Order
from apps.orders.services import sync_esim
from apps.providers.yesim import YesimError

from .serializers import (CountrySerializer, EsimSerializer, OrderSerializer,
                          PlanSerializer, RegionSerializer)
from .throttles import AuthAnonThrottle, CheckoutThrottle


def _tokens(user):
    refresh = RefreshToken.for_user(user)
    return {"access": str(refresh.access_token), "refresh": str(refresh)}


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
    send_welcome(user)
    return Response({"user": {"email": user.email}, **_tokens(user)}, status=201)



@api_view(["POST"])
@permission_classes([AllowAny])
@throttle_classes([AuthAnonThrottle])
def login(request):
    from django.contrib.auth import authenticate

    email = (request.data.get("email") or "").strip().lower()
    user = authenticate(request, username=email, password=request.data.get("password") or "")
    if user is None:
        return Response({"detail": "Incorrect email or password."}, status=400)
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



@api_view(["GET"])
def me(request):
    u = request.user
    return Response({"email": u.email, "display_name": u.display_name,
                     "esim_count": u.esims.filter(is_deleted=False).count()})


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
@throttle_classes([CheckoutThrottle])
def checkout_url(request):
    """Return the WEB checkout URL for a plan — the app opens it in the system
    browser. Payment never happens inside the app (store-policy safe)."""
    plan = Plan.objects.live().filter(pk=request.data.get("plan_id")).first()
    if plan is None:
        return Response({"detail": "Plan not found."}, status=404)
    path = reverse("checkout", kwargs={"plan_id": plan.pk})
    esim_id = request.data.get("esim_id")
    if esim_id and Esim.objects.filter(pk=esim_id, user=request.user).exists():
        path = f"{path}?esim={esim_id}"
    return Response({
        "url": f"{settings.SITE_URL}{path}",
        "plan": PlanSerializer(plan).data,
        "open_in": "external_browser",
    })



@api_view(["GET"])
@permission_classes([AllowAny])
def config(request):
    """Bootstrap payload so the app can render without hardcoding anything."""
    return Response({
        "site_name": settings.SITE_NAME,
        "site_url": settings.SITE_URL,
        "support_email": settings.SUPPORT_EMAIL,
        "currency": "USD",
        "min_supported_version": "1.0.0",
        "country_count": Country.objects.filter(is_active=True).count(),
    })
