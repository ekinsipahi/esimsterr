from django.conf import settings
from django.conf.urls.i18n import i18n_patterns
from django.conf.urls.static import static
from django.contrib import admin
from django.contrib.sitemaps.views import sitemap as sitemap_view
from django.http import JsonResponse
from django.urls import include, path
from django.views.generic import TemplateView

from core.sitemaps import SITEMAPS


def health(_request):
    return JsonResponse({"status": "ok", "service": "esimsterr"})


# Machine endpoints stay OUTSIDE i18n_patterns: a payment provider posting to
# /webhooks/stripe/ must never be redirected to /tr/webhooks/stripe/, and the
# mobile app's API paths must be stable regardless of the caller's Accept-Language.
urlpatterns = [
    path("admin/", admin.site.urls),
    path("health/", health, name="health"),
    path("sitemap.xml", sitemap_view, {"sitemaps": SITEMAPS},
         name="django.contrib.sitemaps.views.sitemap"),
    path("robots.txt", TemplateView.as_view(template_name="robots.txt",
                                            content_type="text/plain")),
    path("i18n/", include("django.conf.urls.i18n")),   # language switcher POST
    path("webhooks/", include("apps.payments.urls")),
    path("api/v1/", include("apps.api.urls")),
]

# Human-facing pages. prefix_default_language=False keeps English on bare paths,
# so adding a locale later never moves an already-indexed URL.
urlpatterns += i18n_patterns(
    path("", include("apps.legal.urls")),
    path("", include("apps.wallet.urls")),
    path("", include("apps.catalog.urls")),
    path("", include("apps.accounts.urls")),
    path("", include("apps.orders.urls")),
    path("", include("apps.support.urls")),
    path("", include("apps.coupons.urls")),
    path("", include("apps.subscriptions.urls")),
    path("", include("apps.seo.urls")),
    path("blog/", include(("apps.blog.urls", "blog"), namespace="blog")),
    prefix_default_language=False,
)

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

admin.site.site_header = "eSIMsterr admin"
admin.site.site_title = "eSIMsterr"
admin.site.index_title = "Operations"
