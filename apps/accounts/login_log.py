"""Record where each account is signed up and signed in from.

Two routes in, because the two surfaces authenticate differently and neither
can cover the other:

* The **website** opens a Django session, so ``user_logged_in`` fires and the
  receiver below catches every path -- including any added later that nobody
  remembers to instrument. A view that knows more than the signal does (which
  method, whether the account was just created) says so by annotating the
  request before calling ``auth_login``.
* The **mobile app** authenticates with a JWT. No session is opened, so no
  signal fires and the receiver never sees it. Those views call
  ``record_login`` themselves. This is why ``signup_ip`` was empty for every
  app user until now.

Nothing in here may break a sign-in. Somebody who cannot get into their account
because an audit row failed to insert is a worse outcome than a gap in the log,
so every entry point swallows its errors and says so in the log instead.
"""
from __future__ import annotations

import logging

from django.contrib.auth.signals import user_logged_in
from django.dispatch import receiver
from django.utils import timezone

from .models import LoginEvent

log = logging.getLogger(__name__)

# Set these on the request before auth_login() to tell the receiver what the
# bare signal cannot know.
METHOD_ATTR = "_esimsterr_login_method"
EVENT_ATTR = "_esimsterr_login_event"


def client_ip(request):
    """The caller's address, as the rest of this project already decides it.

    Deliberately not its own reading of X-Forwarded-For. That header is written
    by the caller, and core.middleware.RealIPMiddleware has already thrown it
    away in favour of CF-Connecting-IP, which Cloudflare overwrites rather than
    appends to. A second implementation here would record whatever address a
    visitor claimed -- and an address that the person being investigated chose
    is worse than no address at all, because it looks like evidence.
    """
    if request is None:
        return None
    from core.ratelimit import client_ip as canonical

    ip = canonical(request)
    return None if ip == "unknown" else ip


def annotate(request, *, method=None, event=None) -> None:
    """Tell the ``user_logged_in`` receiver what this view knows. Safe to call
    on a request that never logs anybody in."""
    if request is None:
        return
    if method:
        setattr(request, METHOD_ATTR, method)
    if event:
        setattr(request, EVENT_ATTR, event)


def record_login(user, request=None, *, event=LoginEvent.Event.LOGIN,
                 method=LoginEvent.Method.EMAIL, surface="web", ip=None):
    """Log one sign-in or sign-up and refresh the account's last-seen address.

    Returns the row, or None if anything went wrong -- callers are not expected
    to check, it is a return value for tests."""
    if user is None or not getattr(user, "pk", None):
        return None
    ip = ip or client_ip(request)
    ua = ""
    if request is not None:
        ua = (request.META.get("HTTP_USER_AGENT") or "")[:300]
    try:
        row = LoginEvent.objects.create(
            user=user, event=event, method=method, surface=surface,
            ip=ip or None, user_agent=ua,
        )
    except Exception:  # noqa: BLE001
        log.exception("could not record %s for %s", event, user.pk)
        return None

    # last_login is Django's, and it is only maintained for session logins --
    # the app's JWT path leaves it frozen at whatever the last website visit
    # was, which reads as "this account is dormant" about somebody who uses it
    # daily. Keep both honest from the one place that sees every sign-in.
    fields = []
    if ip and user.last_login_ip != ip:
        user.last_login_ip = ip
        fields.append("last_login_ip")
    if event == LoginEvent.Event.LOGIN and surface != "web":
        user.last_login = timezone.now()
        fields.append("last_login")
    if fields:
        try:
            user.save(update_fields=fields)
        except Exception:  # noqa: BLE001
            log.exception("could not update last-login fields for %s", user.pk)
    return row


@receiver(user_logged_in, dispatch_uid="esimsterr.accounts.login_log")
def _on_user_logged_in(sender, request, user, **kwargs):
    """Catch-all for the website. Connected in ``AccountsConfig.ready``."""
    record_login(
        user, request,
        event=getattr(request, EVENT_ATTR, LoginEvent.Event.LOGIN),
        method=getattr(request, METHOD_ATTR, LoginEvent.Method.EMAIL),
        surface="web",
    )
