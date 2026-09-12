"""Sitemaps for the programmatic-SEO pages.

Merge SEO_SITEMAPS into core.sitemaps.SITEMAPS; every class here sets
protocol = "https" so the generated URLs match the canonical host.
"""
from django.contrib.sitemaps import Sitemap
from django.urls import reverse

from apps.catalog.models import Plan

from .data import COMPETITORS, PAYMENT_METHODS, USE_CASES


def _catalogue_lastmod():
    """Newest live plan change. Pages whose content is the price list move when
    the catalogue does, so that timestamp is the honest lastmod for them."""
    return (
        Plan.objects.live()
        .order_by("-updated_at")
        .values_list("updated_at", flat=True)
        .first()
    )


class _PricedSitemap(Sitemap):
    """Shared lastmod for the pages that render live prices, fetched once per
    sitemap render rather than once per URL."""

    protocol = "https"
    _lastmod = None

    def lastmod(self, item):
        if self._lastmod is None:
            self._lastmod = _catalogue_lastmod()
        return self._lastmod


class SeoStaticSitemap(_PricedSitemap):
    PAGES = [
        ("cheap_esim", "weekly", 0.8),
        ("prices", "weekly", 0.8),
        ("what_is_esim", "monthly", 0.6),
        ("esim_not_working", "monthly", 0.6),
    ]

    def items(self):
        return [name for name, _c, _p in self.PAGES]

    def location(self, item):
        return reverse(item)

    def changefreq(self, item):
        return dict((n, c) for n, c, _p in self.PAGES)[item]

    def priority(self, item):
        return dict((n, p) for n, _c, p in self.PAGES)[item]

    def lastmod(self, item):
        # The two education pages are editorial, not price-driven.
        if item in ("what_is_esim", "esim_not_working"):
            return None
        return super().lastmod(item)


class PaymentMethodSitemap(_PricedSitemap):
    changefreq = "monthly"
    priority = 0.7

    def items(self):
        return list(PAYMENT_METHODS)

    def location(self, item):
        return reverse("payment_method", kwargs={"slug": item})


class AlternativeSitemap(_PricedSitemap):
    changefreq = "monthly"
    priority = 0.6

    def items(self):
        return list(COMPETITORS)

    def location(self, item):
        return reverse("alternative", kwargs={"slug": item})


class UseCaseSitemap(_PricedSitemap):
    changefreq = "weekly"
    priority = 0.7

    def items(self):
        return list(USE_CASES)

    def location(self, item):
        return reverse("use_case", kwargs={"slug": item})


SEO_SITEMAPS = {
    "seo": SeoStaticSitemap,
    "seo_payments": PaymentMethodSitemap,
    "seo_alternatives": AlternativeSitemap,
    "seo_use_cases": UseCaseSitemap,
}
