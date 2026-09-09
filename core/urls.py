from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.contrib.sitemaps.views import sitemap as sitemap_view
from django.http import JsonResponse
from django.urls import include, path
from django.views.generic import TemplateView

from core.sitemaps import SITEMAPS


def health(_request):
    return JsonResponse({"status": "ok", "service": "esimsterr"})


urlpatterns = [
    path("admin/", admin.site.urls),
    path("health/", health, name="health"),
    path("sitemap.xml", sitemap_view, {"sitemaps": SITEMAPS}, name="django.contrib.sitemaps.views.sitemap"),
    path("robots.txt", TemplateView.as_view(template_name="robots.txt", content_type="text/plain")),
    # Web (server-rendered)
    path("", include("apps.catalog.urls")),
    path("", include("apps.accounts.urls")),
    path("", include("apps.orders.urls")),
    path("", include("apps.support.urls")),
    path("blog/", include(("apps.blog.urls", "blog"), namespace="blog")),
    # Payment webhooks + provider notifications
    path("webhooks/", include("apps.payments.urls")),
    # JSON API for the mobile app (JWT)
    path("api/v1/", include("apps.api.urls")),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

admin.site.site_header = "eSIMsterr admin"
admin.site.site_title = "eSIMsterr"
admin.site.index_title = "Operations"
