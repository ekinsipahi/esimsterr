from django.conf import settings
from django.contrib.sitemaps import Sitemap
from django.urls import reverse


class _CanonicalHost:
    """Stands in for a Sites entry so sitemap URLs never inherit the request host.

    We do not run django.contrib.sites, so Django falls back to RequestSite and
    stamps whatever Host header arrived onto every <loc>. A crawler that reaches
    the Render subdomain would then be handed a sitemap advertising that
    subdomain, splitting the site in two as far as Google is concerned."""

    @property
    def domain(self):
        return settings.CANONICAL_HOST

    name = domain


class CanonicalSitemap(Sitemap):
    protocol = "https"

    def get_urls(self, page=1, site=None, protocol=None):
        return super().get_urls(page=page, site=_CanonicalHost(), protocol="https")

from apps.blog.models import Post
from apps.catalog.models import Country, Region
from apps.seo.sitemaps import SEO_SITEMAPS


class StaticSitemap(CanonicalSitemap):
    protocol = "https"
    PAGES = [
        ("home", "daily", 1.0),
        ("destinations", "daily", 0.9),
        ("regions", "weekly", 0.8),
        ("unlimited", "weekly", 0.8),
        ("coupons", "weekly", 0.7),
        ("how_it_works", "monthly", 0.6),
        ("compatible_devices", "monthly", 0.6),
        ("faq", "monthly", 0.6),
        ("about", "monthly", 0.4),
        ("support", "monthly", 0.5),
        ("blog:index", "weekly", 0.5),
        ("privacy", "yearly", 0.2),
        ("terms", "yearly", 0.2),
        ("refund", "yearly", 0.2),
    ]

    def items(self):
        return [p[0] for p in self.PAGES]

    def location(self, item):
        return reverse(item)

    def changefreq(self, item):
        return dict((n, c) for n, c, _ in self.PAGES)[item]

    def priority(self, item):
        return dict((n, p) for n, _, p in self.PAGES)[item]


class CountrySitemap(CanonicalSitemap):
    protocol = "https"
    changefreq = "weekly"
    priority = 0.8

    def items(self):
        return Country.objects.filter(is_active=True).order_by("slug")

    def lastmod(self, obj):
        return obj.updated_at


class RegionSitemap(CanonicalSitemap):
    protocol = "https"
    changefreq = "weekly"
    priority = 0.7

    def items(self):
        return Region.objects.filter(is_active=True).order_by("slug")

    def lastmod(self, obj):
        return obj.updated_at


class BlogSitemap(CanonicalSitemap):
    protocol = "https"
    changefreq = "monthly"
    priority = 0.5

    def items(self):
        return Post.objects.filter(is_published=True).order_by("-published_at")

    def lastmod(self, obj):
        return obj.updated_at


SITEMAPS = {
    "static": StaticSitemap,
    "countries": CountrySitemap,
    "regions": RegionSitemap,
    "blog": BlogSitemap,
    **SEO_SITEMAPS,
}
