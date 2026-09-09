from django.conf import settings
from django.http import HttpResponsePermanentRedirect


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
