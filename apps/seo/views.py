"""Programmatic-SEO pages: price hub, payment intents, comparisons, education,
troubleshooting, use-case indexes and the full price index.

Two rules run through every view here:

* No price is ever written in Python or in a template. Each page asks the
  catalogue for the cheapest live plan in its own scope, so the headline "from
  just $X" and the tables underneath cannot disagree with the checkout.
* No competitor price is stated anywhere. See the note above COMPETITORS in
  data.py.

The app is deliberately stateless: no models and no migrations.
"""
from __future__ import annotations

import json
from decimal import Decimal

from django.conf import settings
from django.db.models import DecimalField, F, FloatField, Q
from django.db.models.functions import Cast, Coalesce
from django.http import Http404
from django.shortcuts import render
from django.urls import reverse
from django.utils.translation import gettext as _

from apps.common import schema

from apps.catalog.data import POPULAR_ISO2
from apps.catalog.models import Country, Plan, Region

from .data import (
    CHEAP_FAQ,
    COMPARE_ROWS,
    COMPETITORS,
    DIAGNOSTIC_STEPS,
    EDUCATION_FAQ,
    PAYMENT_METHODS,
    PRICES_FAQ,
    SIM_COMPARISON,
    SYMPTOMS,
    TROUBLESHOOTING_FAQ,
    USE_CASES,
)

# A plan's sellable price is the manual override when one exists, otherwise the
# computed retail price — the same rule as Plan.price, expressed in SQL so we can
# sort and pick minimums in the database instead of dragging 1500 rows into Python.
_EFF_PRICE = Coalesce(
    "price_override_usd", "price_usd",
    output_field=DecimalField(max_digits=10, decimal_places=2),
)


def _live():
    return Plan.objects.live().annotate(eff_price=_EFF_PRICE)


def _from_price(qs=None):
    """Cheapest live price in a scope, as a Decimal, or None when nothing is live."""
    qs = _live() if qs is None else qs
    return qs.order_by("eff_price").values_list("eff_price", flat=True).first()


def _money(value):
    """'1.49' — the bare number, because the templates and titles add the $."""
    if value is None:
        return ""
    return f"{Decimal(value).quantize(Decimal('0.01'))}"


def _cheapest_per_country(countries, min_gb=None, min_days=None):
    """Cheapest live plan for each country, preferring one that fits the ask.

    Returns an ordered list of (country, plan). Countries with no live plan are
    dropped rather than rendered as an empty row. Where a country sells nothing
    that meets min_gb / min_days its cheapest plan is still returned, carrying
    plan.fits_ask = False, so a page that promises plans fitting a recommendation
    can mark the row instead of quietly contradicting its own heading.
    """
    countries = [c for c in countries if c]
    if not countries:
        return []
    ids = [c.pk for c in countries]
    plans = list(
        _live()
        .filter(kind=Plan.Kind.COUNTRY, country_id__in=ids)
        .select_related("country")
        .order_by("eff_price")
    )
    best: dict[int, Plan] = {}
    fallback: dict[int, Plan] = {}
    for p in plans:
        fallback.setdefault(p.country_id, p)
        if p.country_id in best:
            continue
        if min_days and p.days < min_days:
            continue
        if min_gb and not p.is_unlimited and (p.data_gb or 0) < min_gb:
            continue
        best[p.country_id] = p
    rows = []
    for c in countries:
        plan = best.get(c.pk)
        fits = plan is not None
        plan = plan or fallback.get(c.pk)
        if plan:
            plan.fits_ask = fits
            rows.append((c, plan))
    return rows


def _countries_by_iso(iso_list):
    """Countries in the order the ISO list gives them, silently skipping any that
    are not live — a destination can be deactivated without breaking a page."""
    by_iso = {c.iso2: c for c in Country.objects.filter(is_active=True, iso2__in=iso_list)}
    return [by_iso[i] for i in iso_list if i in by_iso]


def _faq_jsonld(items):
    return schema.dumps(schema.faq(items))


def _breadcrumb_jsonld(request, crumbs):
    """Kept as a name the views already call; the work is shared now."""
    return schema.dumps(schema.breadcrumbs(request, crumbs))


def _base_ctx(request, *, crumbs, faq=None):
    # site_name, site_url and the org schema come from core.context_processors.site.
    ctx = {
        "breadcrumbs": crumbs,
        "breadcrumb_jsonld": _breadcrumb_jsonld(request, crumbs),
    }
    if faq:
        ctx["faq"] = faq
        ctx["faq_jsonld"] = _faq_jsonld(faq)
    return ctx


def _hub_links():
    """The small set of internal links every page in this app carries. Deliberately
    short: a wall of links on every page is spam, and /esim-prices/ is the one page
    that lists every destination."""
    return [
        (_("All destinations"), reverse("destinations")),
        (_("Price list"), reverse("prices")),
        (_("Regional plans"), reverse("regions")),
        (_("Unlimited plans"), reverse("unlimited")),
        (_("How it works"), reverse("how_it_works")),
    ]


def _use_case_links(limit=None):
    """(label, url) pairs for the use-case pages.

    These and the comparison pages sit two clicks from the homepage and are linked
    sitewide only from the footer, which is the weakest link a page can have. The
    pages in this app that people actually land on carry them in the body instead.
    """
    items = [(c["h1"], reverse("use_case", kwargs={"slug": slug})) for slug, c in USE_CASES.items()]
    return items[:limit] if limit else items


def _alternative_links(limit=None):
    items = [
        (_("%(brand)s alternative") % {"brand": r["name"]},
         reverse("alternative", kwargs={"slug": slug}))
        for slug, r in COMPETITORS.items()
    ]
    return items[:limit] if limit else items


# ---------------------------------------------------------------------------
# 1. Price / deal hub
# ---------------------------------------------------------------------------
def cheap_esim(request):
    price = _from_price()
    popular = _countries_by_iso(POPULAR_ISO2)
    rows = _cheapest_per_country(popular)

    # "Best value right now" — genuinely lowest cost per gigabyte across live
    # country plans, one per destination so a single country cannot fill the table.
    per_gb = (
        _live()
        .filter(kind=Plan.Kind.COUNTRY, is_unlimited=False, data_gb__gte=3)
        .select_related("country")
        .annotate(per_gb=Cast(F("eff_price"), FloatField()) / Cast(F("data_gb"), FloatField()))
        .order_by("per_gb")[:120]
    )
    value_rows, seen = [], set()
    for p in per_gb:
        if p.country_id in seen or not p.country:
            continue
        seen.add(p.country_id)
        value_rows.append(p)
        if len(value_rows) == 12:
            break

    regions = Region.objects.filter(is_active=True).order_by("sort_order", "name")[:6]
    crumbs = [(_("Home"), "/"), (_("Cheap eSIM"), None)]
    ctx = _base_ctx(request, crumbs=crumbs, faq=CHEAP_FAQ)
    ctx.update({
        "from_price": price,
        "from_price_str": _money(price),
        "rows": rows,
        "value_rows": value_rows,
        "regions": regions,
        "hub_links": _hub_links(),
        "related_use_cases": _use_case_links(),
        "related_alternatives": _alternative_links(),
        "country_count": Country.objects.filter(is_active=True).count(),
        "seo_title": _("Cheap eSIM plans — travel data from just $%(price)s") % {"price": _money(price)},
        "seo_description": _(
            "Cheap travel eSIM deals with the price per GB printed on every plan. Live prices from "
            "$%(price)s, instant QR delivery, card or crypto, no account needed."
        ) % {"price": _money(price)},
    })
    return render(request, "seo/cheap.html", ctx)


# ---------------------------------------------------------------------------
# 2. Payment-intent pages
# ---------------------------------------------------------------------------
def payment_method(request, slug):
    method = PAYMENT_METHODS.get(slug)
    if not method:
        raise Http404("Unknown payment method")
    price = _from_price()
    popular = _countries_by_iso(POPULAR_ISO2[:8])
    country_count = Country.objects.filter(is_active=True).count()
    crumbs = [(_("Home"), "/"), (_("Payment methods"), None), (method["label"], None)]
    ctx = _base_ctx(request, crumbs=crumbs, faq=method["faq"])
    ctx.update({
        "method": method,
        "slug": slug,
        "others": [(k, v) for k, v in PAYMENT_METHODS.items() if k != slug],
        "from_price_str": _money(price),
        "rows": _cheapest_per_country(popular),
        "regions": Region.objects.filter(is_active=True).order_by("sort_order", "name")[:6],
        "hub_links": _hub_links(),
        "related_use_cases": _use_case_links(),
        "related_alternatives": _alternative_links(3),
        "country_count": country_count,
        # Both strings are formatted with the same mapping, so a page can quote the
        # live catalogue size without every other page having to mention it.
        "seo_title": str(method["seo_title"]) % {"price": _money(price), "count": country_count},
        "seo_description": str(method["seo_description"]) % {
            "price": _money(price), "count": country_count},
    })
    return render(request, "seo/payment_method.html", ctx)


# ---------------------------------------------------------------------------
# 3. Comparison / alternative pages
# ---------------------------------------------------------------------------
def alternative(request, slug):
    rival = COMPETITORS.get(slug)
    if not rival:
        raise Http404("Unknown comparison")
    price = _from_price()
    popular = _countries_by_iso(POPULAR_ISO2[:8])
    crumbs = [(_("Home"), "/"), (_("Alternatives"), None), (rival["name"], None)]
    ctx = _base_ctx(request, crumbs=crumbs, faq=rival["faq"])
    ctx.update({
        "rival": rival,
        "slug": slug,
        "rows": list(COMPARE_ROWS) + list(rival.get("extra_rows", [])),
        "dest_rows": _cheapest_per_country(popular),
        "others": [(k, v["name"]) for k, v in COMPETITORS.items() if k != slug],
        "related_use_cases": _use_case_links(3),
        "from_price_str": _money(price),
        "country_count": Country.objects.filter(is_active=True).count(),
        "region_count": Region.objects.filter(is_active=True).count(),
        "hub_links": _hub_links(),
        "seo_title": _("%(brand)s alternative — the same networks from just $%(price)s") % {
            "brand": rival["name"], "price": _money(price)},
        "seo_description": _(
            "Looking for an alternative to %(brand)s? Compare on what can be checked: price per GB on "
            "every plan, no account to buy, crypto accepted, no auto-renew. From $%(price)s."
        ) % {"brand": rival["name"], "price": _money(price)},
    })
    return render(request, "seo/alternative.html", ctx)


# ---------------------------------------------------------------------------
# 4. Education
# ---------------------------------------------------------------------------
def what_is_esim(request):
    price = _from_price()
    crumbs = [(_("Home"), "/"), (_("What is an eSIM"), None)]
    ctx = _base_ctx(request, crumbs=crumbs, faq=EDUCATION_FAQ)
    ctx.update({
        "comparison": SIM_COMPARISON,
        "from_price_str": _money(price),
        "popular": _countries_by_iso(POPULAR_ISO2[:8]),
        "hub_links": _hub_links(),
        "related_use_cases": _use_case_links(),
        "related_alternatives": _alternative_links(3),
        "country_count": Country.objects.filter(is_active=True).count(),
        "seo_title": _("What is an eSIM? How it works, and eSIM vs SIM explained"),
        "seo_description": _(
            "An eSIM is a SIM built into your phone that downloads a plan over the internet. How it "
            "works, eSIM vs physical SIM, and which phones support it."
        ),
    })
    return render(request, "seo/what_is_esim.html", ctx)


# ---------------------------------------------------------------------------
# 5. Troubleshooting
# ---------------------------------------------------------------------------
def esim_not_working(request):
    crumbs = [(_("Home"), "/"), (_("eSIM not working"), None)]
    ctx = _base_ctx(request, crumbs=crumbs, faq=TROUBLESHOOTING_FAQ)
    ctx.update({
        "steps": DIAGNOSTIC_STEPS,
        "symptoms": SYMPTOMS,
        "hub_links": _hub_links(),
        "seo_title": _("eSIM not working? Fix it in order, starting with data roaming"),
        "seo_description": _(
            "A travel eSIM with no service or no data is almost always one setting. Work through the "
            "checks in order, starting with data roaming."
        ),
        "meta_robots": "index,follow",
    })
    return render(request, "seo/not_working.html", ctx)


# ---------------------------------------------------------------------------
# 6. Use-case destination indexes
# ---------------------------------------------------------------------------
def use_case(request, slug):
    case = USE_CASES.get(slug)
    if not case:
        raise Http404("Unknown use case")
    countries = _countries_by_iso(case["iso2"])
    rows = _cheapest_per_country(countries, min_gb=case.get("rec_gb"), min_days=case.get("rec_days"))
    # The headline price has to be the cheapest plan that actually fits the
    # recommendation. Quoting the $1.49 one-day plan under a page promising a
    # month of data would be true and useless at the same time.
    scoped = _live().filter(kind=Plan.Kind.COUNTRY, country__in=countries)
    if case.get("rec_days"):
        scoped = scoped.filter(days__gte=case["rec_days"])
    if case.get("rec_gb"):
        scoped = scoped.filter(Q(is_unlimited=True) | Q(data_gb__gte=case["rec_gb"]))
    price = _from_price(scoped) or _from_price(
        _live().filter(kind=Plan.Kind.COUNTRY, country__in=countries)
    ) or _from_price()
    regions = Region.objects.filter(is_active=True, slug__in=case.get("region_slugs", []))
    crumbs = [(_("Home"), "/"), (_("eSIM by use case"), None), (case["h1"], None)]
    ctx = _base_ctx(request, crumbs=crumbs, faq=case["faq"])
    ctx.update({
        "case": case,
        "slug": slug,
        "rows": rows,
        "regions": regions,
        "others": [(k, v["h1"]) for k, v in USE_CASES.items() if k != slug],
        "related_alternatives": _alternative_links(3),
        "from_price_str": _money(price),
        "hub_links": _hub_links(),
        "seo_title": str(case["seo_title"]) % {"price": _money(price)},
        "seo_description": str(case["seo_description"]) % {"price": _money(price)},
    })
    return render(request, "seo/use_case.html", ctx)


# ---------------------------------------------------------------------------
# 7. Price index — the internal-linking hub
# ---------------------------------------------------------------------------
def prices(request):
    continent = (request.GET.get("continent") or "").strip()
    qs = Country.objects.filter(is_active=True)
    continents = sorted({c for c in qs.values_list("continent", flat=True) if c})
    if continent and continent not in continents:
        continent = ""
    if continent:
        qs = qs.filter(continent=continent)
    # nulls_last, because a destination whose price has not synced yet sorts first
    # on SQLite and last on PostgreSQL, and "See plans" rows are not the opening of
    # a price table.
    countries = list(qs.order_by(F("min_price_usd").asc(nulls_last=True), "name"))

    grouped: dict[str, list[Country]] = {}
    for c in sorted(countries, key=lambda x: x.name):
        grouped.setdefault(c.continent or _("Other"), []).append(c)

    price = _from_price()
    crumbs = [(_("Home"), "/"), (_("eSIM prices"), None)]
    if continent:
        crumbs = [(_("Home"), "/"), (_("eSIM prices"), reverse("prices")), (continent, None)]
    ctx = _base_ctx(request, crumbs=crumbs, faq=PRICES_FAQ)
    ctx.update({
        "countries": countries,
        "grouped": sorted(grouped.items()),
        "continent": continent,
        "continents": continents,
        "regions": Region.objects.filter(is_active=True).order_by("sort_order", "name"),
        "unlimited_count": sum(1 for c in countries if c.has_unlimited),
        "from_price_str": _money(price),
        "hub_links": _hub_links(),
        "related_use_cases": _use_case_links(),
        "related_alternatives": _alternative_links(),
        # A filtered view is a slice of the same table: keep it out of the index
        # so the unfiltered page is the one that ranks.
        "meta_robots": "noindex,follow" if continent else "index,follow",
        "seo_title": (
            _("%(continent)s eSIM prices — every country, starting from just $%(price)s") % {
                "continent": continent, "price": _money(price)}
            if continent else
            _("eSIM prices — every country, starting from just $%(price)s") % {"price": _money(price)}
        ),
        "seo_description": _(
            "The full eSIM price list: the from price for every destination we sell and which ones "
            "have unlimited plans. Live from our catalogue, in USD."
        ),
    })
    return render(request, "seo/prices.html", ctx)
