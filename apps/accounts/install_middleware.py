"""Record which app installation is talking to us.

The support id arrives as a header on every API call. Writing a row for it turns
a customer reading a code down the phone into a database lookup -- including for
guests, who have no account to search by.

Throttled through the cache: a row whose `last_seen` is minutes old tells you
everything a row updated on every request would, and the app makes a dozen calls
a screen. Failure is swallowed: a telemetry row must never be the reason a
purchase 500s.
"""
from __future__ import annotations

import logging
import re

from django.core.cache import cache

logger = logging.getLogger(__name__)

SUPPORT_ID = re.compile(r"^ESM-[A-Z2-9]{4}-[A-Z2-9]{4}$")
TOUCH_SECONDS = 900


class AppInstallMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        try:
            self._record(request)
        except Exception:  # noqa: BLE001
            logger.exception("could not record app install")
        return response

    def _record(self, request) -> None:
        if not request.path.startswith("/api/"):
            return
        support_id = (request.headers.get("X-Support-Id") or "").strip().upper()
        if not SUPPORT_ID.match(support_id):
            return

        user = getattr(request, "user", None)
        user = user if getattr(user, "is_authenticated", False) else None
        key = f"install:{support_id}:{getattr(user, 'pk', '')}"
        if cache.get(key):
            return
        cache.set(key, 1, TOUCH_SECONDS)

        from apps.accounts.models import AppInstall

        platform = (request.headers.get("X-Client-Platform") or "android")[:12]
        version = (request.headers.get("X-Client-Version") or "")[:20]
        install, _created = AppInstall.objects.get_or_create(
            support_id=support_id,
            defaults={"platform": platform, "app_version": version, "user": user},
        )
        fields = []
        if install.app_version != version and version:
            install.app_version = version
            fields.append("app_version")
        if user is not None and install.user_id != user.pk:
            # The install signed in, or signed in as somebody else. Either way
            # the current owner is the useful answer for support.
            install.user = user
            fields.append("user")
        # auto_now keeps last_seen fresh on any save.
        install.save(update_fields=fields + ["last_seen"] if fields else ["last_seen"])
