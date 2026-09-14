import json
import logging

from django.conf import settings
from django.contrib import messages
from django.utils.translation import gettext_lazy as _
from django.contrib.auth import login as auth_login, logout as auth_logout, update_session_auth_hash
from django.contrib.auth import views as auth_views
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.urls import reverse, reverse_lazy
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from apps.common import analytics
from apps.legal.models import LegalAcceptance, record_acceptance
from core.ratelimit import rate_limit

from .emails import send_email_bg, send_welcome
from .forms import LoginForm, PasswordChangeForm, ProfileForm, SignupForm
from .google import GoogleAuthError, user_from_google_token
from .referrals import apply_referral_code
from .models import User

log = logging.getLogger(__name__)


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
        # Priority: what they typed, then a campaign link, then the cookie a
        # previous visit left. The typed one wins because it is the only one
        # they can see, and being overridden by an invisible cookie is the kind
        # of thing that turns into a support ticket about a missing bonus.
        ref = (form.cleaned_data.get("referral_code")
               or request.session.pop("ref_code", None)
               or request.COOKIES.get("ref"))
        apply_referral_code(user, ref)
        auth_login(request, user, backend="django.contrib.auth.backends.ModelBackend")
        record_acceptance(request, user=user, email=user.email,
                          context=LegalAcceptance.Context.SIGNUP)
        send_welcome(user)
        request.session["pending_analytics"] = [analytics.sign_up("email")]
        return redirect(_safe_next(request))
    return render(request, "accounts/signup.html", {
        "form": form, "next": request.GET.get("next", ""),
        # A code in the URL pre-fills the field rather than being applied
        # silently, so the new customer can see who invited them.
        "ref_prefill": (request.GET.get("ref") or request.session.get("ref_code") or "").upper(),
        "referral_bonus": settings.REFERRAL_BONUS_USD,
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
        request.session["pending_analytics"] = [analytics.login("email")]
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
    """Google Identity Services callback: an ID token in, a session out.

    Two kinds of caller reach this, and they need different answers. The sign-in
    page submits a real form, so the browser navigates to whatever comes back:
    that caller must get a redirect, or the customer lands staring at raw JSON.
    The mobile app and any fetch() caller want the JSON. Content negotiation
    decides, rather than a second URL."""
    wants_json = (
        request.headers.get("X-Requested-With") == "XMLHttpRequest"
        or "application/json" in request.headers.get("Accept", "")
        or request.content_type == "application/json"
    )

    def fail(message, status):
        if wants_json:
            return JsonResponse({"ok": False, "error": message}, status=status)
        messages.error(request, message)
        return redirect("login")

    token = request.POST.get("credential") or ""
    if not token:
        try:
            token = json.loads(request.body.decode() or "{}").get("credential", "")
        except ValueError:
            token = ""
    if not token:
        return fail(_("Google sign-in did not return a token. Please try again."), 400)
    try:
        user, created = user_from_google_token(token, signup_ip=_client_ip(request))
    except GoogleAuthError as e:
        # The underlying library reports things like "Wrong number of segments in
        # token: b'...'", which is useful in a log and meaningless on a sign-in
        # page. The detail goes to the logs and to API callers; the person
        # reading the page gets something they can act on.
        log.warning("Google sign-in rejected: %s", e)
        if wants_json:
            return JsonResponse({"ok": False, "error": str(e)}, status=400)
        return fail(_("Google could not verify that sign-in. Please try again, "
                      "or use your email address."), 400)
    if not user.is_active:
        return fail(_("This account is disabled."), 403)

    auth_login(request, user, backend="django.contrib.auth.backends.ModelBackend")
    if created:
        send_welcome(user)
    request.session["pending_analytics"] = [
        analytics.sign_up("google") if created else analytics.login("google")
    ]
    destination = _safe_next(request)
    if wants_json:
        return JsonResponse({"ok": True, "next": destination})
    return redirect(destination)


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
            # Deletion has its own page. It cancels billing, erases support
            # history and has to say so before the click, which does not fit
            # under a settings form.
            return redirect("account_delete")
    return render(request, "dashboard/account.html", {
        "profile_form": profile_form, "pw_form": pw_form,
        "seo_title": "Account — eSIMsterr", "meta_robots": "noindex,nofollow",
    })


def account_delete(request):
    """Delete your own account, without emailing anyone to ask.

    Deliberately reachable when signed out. Google Play requires the deletion
    route to be findable from outside the app, and a page that bounces a signed
    -out visitor to a login form does not meet that -- so the explanation is
    public and only the button needs an account.
    """
    ctx = {
        "seo_title": _("Delete your account — %(site)s") % {"site": settings.SITE_NAME},
        "seo_description": _("How to delete your %(site)s account and what happens to your "
                             "data when you do.") % {"site": settings.SITE_NAME},
        "meta_robots": "noindex,follow",
    }
    if not request.user.is_authenticated:
        return render(request, "dashboard/account_delete.html", ctx)

    from .deletion import DeletionBlocked, active_subscriptions, delete_account

    subs = list(active_subscriptions(request.user))
    ctx["active_subscriptions"] = subs

    if request.method == "POST":
        if request.POST.get("confirm", "").strip().upper() != "DELETE":
            messages.error(request, _("Type DELETE to confirm."))
            return render(request, "dashboard/account_delete.html", ctx)

        user, email = request.user, request.user.email
        try:
            report = delete_account(user)
        except DeletionBlocked as e:
            log.warning("Account deletion blocked for %s: %s", user.pk, e)
            messages.error(request, str(e))
            return render(request, "dashboard/account_delete.html", ctx)

        auth_logout(request)
        send_email_bg(email, f"Your {settings.SITE_NAME} account has been deleted",
                      "account_deleted", {"lines": report.as_lines()})
        messages.success(request, _("Your account has been deleted. A confirmation is on "
                                    "its way to your email."))
        return redirect("home")

    return render(request, "dashboard/account_delete.html", ctx)


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
