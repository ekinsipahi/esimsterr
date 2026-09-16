from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import validate_ipv46_address
from django.http import HttpResponsePermanentRedirect


class RealClientIPMiddleware:
    """Work out who is actually calling, before anything counts or records it.

    The old answer was the first entry of X-Forwarded-For, and that entry is
    written by the caller. Cloudflare appends the connecting address to whatever
    chain it was handed rather than replacing it, so a request carrying
    `X-Forwarded-For: 1.2.3.4` arrives as `1.2.3.4, <real client>, <cloudflare>`
    and reading the front of it gives you a value the attacker chose. Every
    per-IP limit in the project keys on that value -- sign-in attempts, checkout,
    coupon tries, the support form -- so all of them could be reset at will by
    changing one header, and the IP stored against a guest order was whatever
    the buyer felt like claiming.

    CF-Connecting-IP is the field Cloudflare overwrites rather than appends to,
    so it is the one that means something. The chain itself is deliberately not
    consulted as a fallback: no position in it is trustworthy without knowing
    exactly how many proxies added to it, the front is the caller's to write, and
    the back is our own edge. When the header is missing -- a request that did
    not come through Cloudflare -- the socket address is the only honest answer,
    even though it groups everyone behind the same edge into one bucket.

    The result is written back over both REMOTE_ADDR and X-Forwarded-For so that
    everything downstream agrees: DRF's throttles read the header directly and
    would otherwise key on the attacker-supplied chain no matter what the rest of
    the code decided.
    """

    HEADER = "HTTP_CF_CONNECTING_IP"

    def __init__(self, get_response):
        self.get_response = get_response
        self.header = getattr(settings, "REAL_IP_HEADER", self.HEADER)

    @staticmethod
    def _valid(candidate: str) -> str:
        candidate = (candidate or "").strip()
        if not candidate:
            return ""
        try:
            validate_ipv46_address(candidate)
        except ValidationError:
            return ""
        return candidate

    def __call__(self, request):
        meta = request.META
        ip = self._valid(meta.get(self.header, "")) or self._valid(meta.get("REMOTE_ADDR", ""))
        if ip:
            meta["REMOTE_ADDR"] = ip
            meta["HTTP_X_FORWARDED_FOR"] = ip
        else:
            meta.pop("HTTP_X_FORWARDED_FOR", None)
        return self.get_response(request)


class DomainRedirectMiddleware:
    """301 alias hosts (www., onrender.com) to the canonical host, keeping path+query."""

    def __init__(self, get_response):
        self.get_response = get_response
        self.canonical = getattr(settings, "CANONICAL_HOST", "")
        self.redirect_hosts = {h.lower() for h in getattr(settings, "REDIRECT_HOSTS", [])}

    def __call__(self, request):
        host = (request.get_host() or "").split(":")[0].lower()
        if self.canonical and host in self.redirect_hosts and host != self.canonical:
            return HttpResponsePermanentRedirect(f"https://{self.canonical}{request.get_full_path()}")
        return self.get_response(request)


class CoopAllowPopupsMiddleware:
    """Google Identity Services popup needs COOP=same-origin-allow-popups on auth pages."""

    PATH_PREFIXES = ("/login", "/signup", "/checkout", "/auth/")

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        resp = self.get_response(request)
        if request.path.startswith(self.PATH_PREFIXES):
            resp["Cross-Origin-Opener-Policy"] = "same-origin-allow-popups"
        return resp
