import json

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import login as auth_login, logout as auth_logout, update_session_auth_hash
from django.contrib.auth import views as auth_views
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.urls import reverse, reverse_lazy
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from core.ratelimit import rate_limit

from .emails import send_welcome
from .forms import LoginForm, PasswordChangeForm, ProfileForm, SignupForm
from .google import GoogleAuthError, user_from_google_token
from .models import User


def _client_ip(request):
    xff = request.META.get("HTTP_X_FORWARDED_FOR", "")
    return (xff.split(",")[0].strip() if xff else request.META.get("REMOTE_ADDR")) or None


def _safe_next(request, default="/dashboard/"):
    nxt = request.POST.get("next") or request.GET.get("next") or ""
    if nxt and url_has_allowed_host_and_scheme(nxt, allowed_hosts={request.get_host()}):
        return nxt
    return default


@rate_limit("signup", limit=6, window=3600)
def signup(request):
    if request.user.is_authenticated:
        return redirect(_safe_next(request))
    form = SignupForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        user = User.objects.create_user(
            email=form.cleaned_data["email"],
            password=form.cleaned_data["password"],
            marketing_opt_in=form.cleaned_data.get("marketing_opt_in", True),
            signup_ip=_client_ip(request),
        )
        ref = request.session.pop("ref_code", None) or request.COOKIES.get("ref")
        if ref:
            referrer = User.objects.filter(referral_code=ref).first()
            if referrer and referrer != user:
                user.referred_by = referrer
                user.save(update_fields=["referred_by"])
        auth_login(request, user, backend="django.contrib.auth.backends.ModelBackend")
        send_welcome(user)
        return redirect(_safe_next(request))
    return render(request, "accounts/signup.html", {
        "form": form, "next": request.GET.get("next", ""),
        "seo_title": "Create your account — eSIMsterr",
        "seo_description": "Create a free eSIMsterr account to buy, install and manage travel eSIMs.",
        "meta_robots": "noindex,follow",
    })


@rate_limit("login", limit=12, window=600)
def login_view(request):
    if request.user.is_authenticated:
        return redirect(_safe_next(request))
    form = LoginForm(request, request.POST or None)
    if request.method == "POST" and form.is_valid():
        auth_login(request, form.user, backend="django.contrib.auth.backends.ModelBackend")
        return redirect(_safe_next(request))
    return render(request, "accounts/login.html", {
        "form": form, "next": request.GET.get("next", ""),
        "seo_title": "Sign in — eSIMsterr",
        "seo_description": "Sign in to manage your eSIMs, view QR codes and top up data.",
        "meta_robots": "noindex,follow",
    })


@require_POST
def logout_view(request):
    auth_logout(request)
    return redirect("home")


@require_POST
@rate_limit("google", limit=12, window=600)
def google_finish(request):
    """GIS callback: POST credential (ID token) → session login. Returns JSON."""
    token = request.POST.get("credential") or ""
    if not token:
        try:
            token = json.loads(request.body.decode() or "{}").get("credential", "")
        except ValueError:
            token = ""
    if not token:
        return JsonResponse({"ok": False, "error": "missing_token"}, status=400)
    try:
        user, created = user_from_google_token(token, signup_ip=_client_ip(request))
    except GoogleAuthError as e:
        return JsonResponse({"ok": False, "error": str(e)}, status=400)
    if not user.is_active:
        return JsonResponse({"ok": False, "error": "account_disabled"}, status=403)
    auth_login(request, user, backend="django.contrib.auth.backends.ModelBackend")
    if created:
        send_welcome(user)
    return JsonResponse({"ok": True, "next": _safe_next(request)})


@login_required
def account(request):
    profile_form = ProfileForm(instance=request.user)
    pw_form = PasswordChangeForm(request.user)
    if request.method == "POST":
        action = request.POST.get("action")
        if action == "profile":
            profile_form = ProfileForm(request.POST, instance=request.user)
            if profile_form.is_valid():
                profile_form.save()
                messages.success(request, "Profile updated.")
                return redirect("account")
        elif action == "password":
            pw_form = PasswordChangeForm(request.user, request.POST)
            if pw_form.is_valid():
                request.user.set_password(pw_form.cleaned_data["new_password"])
                request.user.save(update_fields=["password"])
                update_session_auth_hash(request, request.user)
                messages.success(request, "Password updated.")
                return redirect("account")
        elif action == "delete":
            if request.POST.get("confirm") == "DELETE":
                user = request.user
                auth_logout(request)
                user.is_active = False
                user.email = f"deleted-{user.id}@deleted.invalid"
                user.set_unusable_password()
                user.save(update_fields=["is_active", "email", "password"])
                messages.success(request, "Your account has been deleted.")
                return redirect("home")
            messages.error(request, "Type DELETE to confirm account deletion.")
    return render(request, "dashboard/account.html", {
        "profile_form": profile_form, "pw_form": pw_form,
        "seo_title": "Account — eSIMsterr", "meta_robots": "noindex,nofollow",
    })


def unsubscribe(request):
    token = request.GET.get("t", "")
    user = User.objects.filter(unsubscribe_token=token).first() if token else None
    if user:
        user.marketing_opt_in = False
        user.save(update_fields=["marketing_opt_in"])
    return render(request, "accounts/unsubscribed.html", {"ok": bool(user), "meta_robots": "noindex,nofollow"})


class PasswordResetView(auth_views.PasswordResetView):
    template_name = "accounts/password_reset_form.html"
    # Django's own form builds the email context, so the shared email shell's
    # variables (site_name / site_url / support_email) have to be injected here.
    extra_email_context = {
        "site_name": settings.SITE_NAME,
        "site_url": settings.SITE_URL,
        "support_email": settings.SUPPORT_EMAIL,
    }
    email_template_name = "emails/password_reset.txt"
    html_email_template_name = "emails/password_reset.html"
    subject_template_name = "emails/password_reset_subject.txt"
    success_url = reverse_lazy("password_reset_done")
    extra_context = {"meta_robots": "noindex,follow", "seo_title": "Reset password — eSIMsterr"}


class PasswordResetDoneView(auth_views.PasswordResetDoneView):
    template_name = "accounts/password_reset_done.html"
    extra_context = {"meta_robots": "noindex,follow"}


class PasswordResetConfirmView(auth_views.PasswordResetConfirmView):
    template_name = "accounts/password_reset_confirm.html"
    success_url = reverse_lazy("password_reset_complete")
    extra_context = {"meta_robots": "noindex,nofollow"}


class PasswordResetCompleteView(auth_views.PasswordResetCompleteView):
    template_name = "accounts/password_reset_complete.html"
    extra_context = {"meta_robots": "noindex,follow"}
