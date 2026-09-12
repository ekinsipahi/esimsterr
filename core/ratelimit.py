"""Cache-backed rate limiting for regular Django views.

DRF throttles only cover the JSON API. These same-shaped limits protect the
server-rendered POST endpoints that create rows or call a paid third-party API
(checkout creates orders and provider invoices; signup creates users; support
creates tickets and sends email).

Backed by whatever CACHES is configured — LocMemCache per process in dev, which
is enough to stop casual abuse; point CACHES at Redis if you need it shared
across workers.
"""
from __future__ import annotations

import functools
import time

from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.core.validators import validate_ipv46_address
from django.http import JsonResponse
from django.shortcuts import render


def client_ip(request) -> str:
    """Best-effort caller address for the rate-limit key.

    X-Forwarded-For is attacker-controlled, so a junk value is discarded rather
    than used: an unvalidated header would otherwise let someone rotate garbage
    through it and get a fresh bucket on every request, which is the opposite of
    a rate limit."""
    xff = request.META.get("HTTP_X_FORWARDED_FOR", "")
    candidate = (xff.split(",")[0].strip() if xff else "") or request.META.get("REMOTE_ADDR", "")
    if candidate:
        try:
            validate_ipv46_address(candidate)
            return candidate
        except ValidationError:
            pass
    return "unknown"


def rate_limit(key: str, limit: int, window: int, methods=("POST",)):
    """Allow `limit` requests per `window` seconds per IP for the given methods.

    Over the limit: JSON gets 429, a normal page gets a friendly 429 template.
    """
    def decorator(view):
        @functools.wraps(view)
        def wrapper(request, *args, **kwargs):
            if request.method not in methods:
                return view(request, *args, **kwargs)
            cache_key = f"rl:{key}:{client_ip(request)}"
            now = time.time()
            hits = [t for t in (cache.get(cache_key) or []) if now - t < window]
            if len(hits) >= limit:
                retry_after = int(window - (now - hits[0])) + 1
                if request.headers.get("Accept", "").startswith("application/json") or \
                        request.headers.get("X-Requested-With") == "XMLHttpRequest":
                    resp = JsonResponse({"detail": "Too many requests. Slow down."}, status=429)
                else:
                    resp = render(request, "429.html", {
                        "retry_after": retry_after,
                        "meta_robots": "noindex,nofollow",
                    }, status=429)
                resp["Retry-After"] = str(retry_after)
                return resp
            hits.append(now)
            cache.set(cache_key, hits, window)
            return view(request, *args, **kwargs)
        return wrapper
    return decorator
