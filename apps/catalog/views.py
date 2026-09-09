"""Public catalogue pages: home, destination browser, country/region detail, SEO pages."""
from __future__ import annotations

import json

from django.conf import settings
from django.db.models import Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, render
from django.views.decorators.http import require_GET

from apps.blog.models import Post

from .data import POPULAR_ISO2
from .models import Country, Device, Plan, Region


def _plan_groups(target):
    """Split a destination's live plans into the two tabs the UI shows."""
    plans = list(target.plans.live().select_related("country", "region"))
    data_plans = sorted(
        [p for p in plans if not p.is_unlimited],
        key=lambda p: (p.days, p.data_gb or 0),
    )
    unlimited = sorted([p for p in plans if p.is_unlimited], key=lambda p: p.days)
    return data_plans, unlimited


def _popular_countries(limit=12):
    qs = Country.objects.filter(is_active=True, iso2__in=POPULAR_ISO2)
    by_iso = {c.iso2: c for c in qs}
    ordered = [by_iso[i] for i in POPULAR_ISO2 if i in by_iso]
    return ordered[:limit]


def home(request):
    regions = Region.objects.filter(is_active=True)[:8]
    cheapest = (
        Plan.objects.live()
        .filter(kind=Plan.Kind.COUNTRY, country__is_popular=True)
        .select_related("country")
        .order_by("price_usd")[:8]
    )
    posts = Post.objects.filter(is_published=True).order_by("-published_at")[:3]
    ctx = {
        "popular": _popular_countries(),
        "regions": regions,
        "cheapest": cheapest,
        "posts": posts,
        "country_count": Country.objects.filter(is_active=True).count(),
        "seo_title": f"Travel eSIM for 150+ countries — instant data plans | {settings.SITE_NAME}",
        "seo_description": settings.DEFAULT_DESCRIPTION,
        "faq": HOME_FAQ,
        "faq_jsonld": _faq_jsonld(HOME_FAQ),
    }
    return render(request, "catalog/home.html", ctx)


def destinations(request):
    q = (request.GET.get("q") or "").strip()
    continent = (request.GET.get("continent") or "").strip()
    qs = Country.objects.filter(is_active=True)
    if q:
        qs = qs.filter(Q(name__icontains=q) | Q(iso2__iexact=q) | Q(iso3__iexact=q))
    if continent:
        qs = qs.filter(continent=continent)
    countries = list(qs.order_by("name"))
    grouped: dict[str, list[Country]] = {}
    for c in countries:
        grouped.setdefault(c.continent or "Other", []).append(c)
    ctx = {
        "countries": countries,
        "grouped": sorted(grouped.items()),
        "regions": Region.objects.filter(is_active=True),
        "q": q,
        "continent": continent,
        "continents": sorted({c.continent for c in Country.objects.filter(is_active=True) if c.continent}),
        "seo_title": f"eSIM destinations — data plans for {len(countries)} countries | {settings.SITE_NAME}",
        "seo_description": (
            "Browse prepaid travel eSIM plans by country. Instant QR delivery, no roaming fees, "
            "local 4G/5G networks in 150+ destinations."
        ),
    }
    return render(request, "catalog/destinations.html", ctx)


def country_detail(request, slug):
    country = get_object_or_404(Country, slug=slug, is_active=True)
    data_plans, unlimited = _plan_groups(country)
    nearby = (
        Country.objects.filter(is_active=True, continent=country.continent)
        .exclude(pk=country.pk)
        .order_by("-is_popular", "name")[:8]
    )
    regions = country.regions.filter(is_active=True)
    faq = _country_faq(country)
    ctx = {
        "country": country,
        "target": country,
        "data_plans": data_plans,
        "unlimited_plans": unlimited,
        "nearby": nearby,
        "regions": regions,
        "faq": faq,
        "faq_jsonld": _faq_jsonld(faq),
        "product_jsonld": _product_jsonld(request, country, data_plans + unlimited),
        "breadcrumbs": [("Home", "/"), ("Destinations", "/destinations/"), (country.name, None)],
        "seo_title": country.seo_title or (
            f"{country.name} eSIM — prepaid travel data from ${country.min_price_usd or ''} | {settings.SITE_NAME}"
        ),
        "seo_description": country.seo_description or (
            f"Buy a {country.name} travel eSIM with instant QR delivery. Local 4G/5G data, "
            f"no roaming fees, unlimited options. Install before you fly."
        ),
    }
    return render(request, "catalog/country_detail.html", ctx)


def regions_index(request):
    ctx = {
        "regions": Region.objects.filter(is_active=True),
        "seo_title": f"Regional & global eSIM plans — one eSIM, many countries | {settings.SITE_NAME}",
        "seo_description": (
            "Multi-country travel eSIMs: Europe, Asia, Latin America, Middle East and a global plan "
            "covering 100+ destinations. One QR code for the whole trip."
        ),
    }
    return render(request, "catalog/regions.html", ctx)


def region_detail(request, slug):
    region = get_object_or_404(Region, slug=slug, is_active=True)
    data_plans, unlimited = _plan_groups(region)
    faq = _region_faq(region)
    ctx = {
        "region": region,
        "target": region,
        "data_plans": data_plans,
        "unlimited_plans": unlimited,
        "covered": region.countries.filter(is_active=True).order_by("name"),
        "other_regions": Region.objects.filter(is_active=True).exclude(pk=region.pk)[:6],
        "faq": faq,
        "faq_jsonld": _faq_jsonld(faq),
        "product_jsonld": _product_jsonld(request, region, data_plans + unlimited),
        "breadcrumbs": [("Home", "/"), ("Regions", "/regions/"), (region.name, None)],
        "seo_title": region.seo_title or (
            f"{region.name} eSIM — one plan for {region.country_count} countries | {settings.SITE_NAME}"
        ),
        "seo_description": region.seo_description or (
            f"{region.name} travel eSIM covering {region.country_count} countries. Instant QR delivery, "
            "local networks, unlimited options."
        ),
    }
    return render(request, "catalog/region_detail.html", ctx)


def unlimited(request):
    plans = (
        Plan.objects.live()
        .filter(is_unlimited=True)
        .select_related("country", "region")
        .order_by("price_usd")
    )
    countries = (
        Country.objects.filter(is_active=True, has_unlimited=True)
        .order_by("-is_popular", "name")
    )
    ctx = {
        "plans": plans[:60],
        "countries": countries,
        "regions": Region.objects.filter(is_active=True, has_unlimited=True),
        "seo_title": f"Unlimited data eSIM — truly unlimited travel plans | {settings.SITE_NAME}",
        "seo_description": (
            "Unlimited data eSIMs for 7, 15 or 30 days in 100+ countries. No throttling games, "
            "no roaming bills — one QR code and you're online."
        ),
    }
    return render(request, "catalog/unlimited.html", ctx)


def how_it_works(request):
    return render(request, "pages/how_it_works.html", {
        "seo_title": f"How eSIM works — install in 3 steps | {settings.SITE_NAME}",
        "seo_description": (
            "What an eSIM is, how to install one with a QR code, when your plan starts and how to "
            "keep your WhatsApp number while travelling."
        ),
        "faq": HOME_FAQ,
        "faq_jsonld": _faq_jsonld(HOME_FAQ),
    })


def compatible_devices(request):
    devices = Device.objects.all()
    brands: dict[str, list[str]] = {}
    for d in devices:
        brands.setdefault(d.brand, []).append(d.model)
    return render(request, "pages/devices.html", {
        "brands": sorted(brands.items()),
        "device_count": devices.count(),
        "seo_title": f"eSIM compatible devices — full phone & tablet list | {settings.SITE_NAME}",
        "seo_description": (
            "Check if your iPhone, Samsung, Google Pixel or tablet supports eSIM. Full compatibility "
            "list plus how to check on your device in 10 seconds."
        ),
    })


def faq(request):
    return render(request, "pages/faq.html", {
        "faq": HOME_FAQ + EXTRA_FAQ,
        "faq_jsonld": _faq_jsonld(HOME_FAQ + EXTRA_FAQ),
        "seo_title": f"eSIM FAQ — activation, coverage, refunds | {settings.SITE_NAME}",
        "seo_description": "Answers about eSIM activation, coverage, data top-ups, refunds and device support.",
    })


def about(request):
    return render(request, "pages/about.html", {
        "seo_title": f"About {settings.SITE_NAME}",
        "seo_description": f"{settings.SITE_NAME} sells prepaid travel eSIMs at honest prices, with instant delivery and no roaming bills.",
    })


def legal(request, page):
    templates = {
        "privacy": ("pages/privacy.html", "Privacy Policy"),
        "terms": ("pages/terms.html", "Terms of Service"),
        "refund": ("pages/refund.html", "Refund Policy"),
    }
    template, title = templates[page]
    return render(request, template, {
        "seo_title": f"{title} — {settings.SITE_NAME}",
        "seo_description": f"{title} for {settings.SITE_NAME} travel eSIM plans.",
    })


@require_GET
def search_api(request):
    """Type-ahead for the hero search box: countries + regions, JSON."""
    q = (request.GET.get("q") or "").strip()
    results = []
    if len(q) >= 1:
        for c in Country.objects.filter(is_active=True).filter(
            Q(name__istartswith=q) | Q(iso2__iexact=q)
        ).order_by("-is_popular", "name")[:8]:
            results.append({
                "type": "country", "name": c.name, "url": c.get_absolute_url(),
                "flag": c.flag_emoji, "from": str(c.min_price_usd or ""), "iso2": c.iso2,
            })
        if len(results) < 8:
            for c in Country.objects.filter(is_active=True, name__icontains=q).exclude(
                name__istartswith=q
            ).order_by("name")[: 8 - len(results)]:
                results.append({
                    "type": "country", "name": c.name, "url": c.get_absolute_url(),
                    "flag": c.flag_emoji, "from": str(c.min_price_usd or ""), "iso2": c.iso2,
                })
        for r in Region.objects.filter(is_active=True, name__icontains=q)[:4]:
            results.append({
                "type": "region", "name": r.name, "url": r.get_absolute_url(),
                "flag": r.icon, "from": str(r.min_price_usd or ""),
                "note": f"{r.country_count} countries",
            })
    return JsonResponse({"results": results})


# ---------------------------------------------------------------------------
# FAQ content + JSON-LD helpers
# ---------------------------------------------------------------------------
HOME_FAQ = [
    ("What is an eSIM and how does it work?",
     "An eSIM is a digital SIM already built into your phone. Instead of a plastic card you scan a QR "
     "code, which downloads a mobile data profile onto the device. Your normal SIM stays in place, so "
     "you keep your own number for calls and WhatsApp while the eSIM carries your data abroad."),
    ("How fast do I get my eSIM?",
     "Immediately. As soon as the payment clears, the QR code appears on the confirmation page and in "
     "your account, and we email it to you. There is nothing to ship and nothing to collect."),
    ("When does my plan start counting down?",
     "The clock starts when the eSIM first connects to a network at your destination, not when you "
     "install it. Install it at home on Wi-Fi and it will simply wait until you land."),
    ("Can I still use WhatsApp with my own number?",
     "Yes. WhatsApp, Telegram and iMessage stay tied to your existing number because your physical SIM "
     "is untouched. The eSIM only supplies data."),
    ("Are calls and SMS included?",
     "Plans are data-only. You can call and message over WhatsApp, FaceTime, Telegram, Zoom or any "
     "other app, which is what almost everyone uses abroad anyway."),
    ("Can I share the connection over hotspot?",
     "Yes, personal hotspot works on our plans, so you can put a laptop or a travel companion online "
     "from the same eSIM."),
    ("Which phones support eSIM?",
     "iPhone XS and newer, Google Pixel 3 and newer, Samsung Galaxy S20 and newer, and many recent "
     "Xiaomi, Motorola, Huawei and Oppo models. The phone also has to be carrier-unlocked."),
    ("What if I run out of data?",
     "Buy a top-up from your dashboard. The data is added to the same eSIM, so you never reinstall "
     "anything or scan a second QR code."),
]

EXTRA_FAQ = [
    ("Do I need to show a passport or pass KYC?",
     "No. For the destinations we sell there is no identity verification. You buy, you get a QR code, "
     "you go online."),
    ("Which payment methods do you take?",
     "Cards through Stripe, plus major cryptocurrencies (BTC, ETH, USDT, TRX and more) through "
     "NOWPayments. Prices are shown in US dollars."),
    ("Can I get a refund?",
     "Yes, if the eSIM has not been installed and has no usage, we refund it within 24 hours of "
     "purchase. Once a profile is installed and has used data it cannot be resold, so it is not "
     "refundable. Full detail is in the refund policy."),
    ("Will my eSIM work on two phones?",
     "No. An eSIM profile can only be installed on one device, and on most phones it cannot be moved "
     "once installed. Install it on the phone you will actually travel with."),
    ("Do you keep my browsing data?",
     "No. We never see your traffic. We only store what is needed to sell and support the eSIM: your "
     "email, your orders and the usage counter the network reports."),
]


def _country_faq(country):
    ops = ", ".join(country.operator_list[:3]) or "top-tier local carriers"
    return [
        (f"How does an eSIM work in {country.name}?",
         f"Your {country.name} eSIM connects to local networks ({ops}) exactly like a local SIM would, "
         f"so you pay local data prices instead of roaming rates. Scan the QR code we send you, land, "
         f"and the data turns on by itself."),
        (f"Can I install the {country.name} eSIM before I travel?",
         "Yes, and you should. Install it at home on Wi-Fi; the plan only starts counting when it first "
         f"connects to a network in {country.name}."),
        (f"Will I pay roaming fees in {country.name}?",
         f"No. The eSIM buys data directly from {country.name} networks, so there is no roaming charge "
         "and no bill shock when you get home."),
        (f"Can I make calls in {country.name}?",
         "The plan carries data only. Calls and messages go over WhatsApp, FaceTime, Telegram or any "
         "other app, and your own number stays reachable on your normal SIM."),
        (f"How much data do I need for {country.name}?",
         "For a week of maps, messaging and light browsing, 3–5 GB is comfortable. If you stream, "
         "video-call or share a hotspot, take 10 GB or an unlimited plan."),
    ]


def _region_faq(region):
    return [
        (f"How many countries does the {region.name} eSIM cover?",
         f"{region.country_count} countries on a single profile. You cross a border and the eSIM "
         "reconnects to the next local network on its own."),
        ("Do I need a separate eSIM for each country?",
         f"No. That is the whole point of the {region.name} plan: one QR code, one price, and coverage "
         "across the entire trip."),
        ("When does the plan start?",
         "When the eSIM first connects to a network in any covered country. Install it before you fly "
         "and nothing starts early."),
        ("Is a regional plan cheaper than buying each country?",
         "For two or more countries, almost always. A single-country plan is only cheaper if you truly "
         "stay in one place."),
    ]


def _faq_jsonld(items):
    return json.dumps({
        "@context": "https://schema.org",
        "@type": "FAQPage",
        "mainEntity": [
            {"@type": "Question", "name": q,
             "acceptedAnswer": {"@type": "Answer", "text": a}}
            for q, a in items
        ],
    }, ensure_ascii=False)


def _product_jsonld(request, target, plans):
    if not plans:
        return ""
    offers = [{
        "@type": "Offer",
        "name": p.title,
        "price": f"{p.price:.2f}",
        "priceCurrency": "USD",
        "availability": "https://schema.org/InStock",
        "url": request.build_absolute_uri(p.get_absolute_url()),
    } for p in plans[:30]]
    return json.dumps({
        "@context": "https://schema.org",
        "@type": "Product",
        "name": f"{target.name} travel eSIM",
        "description": f"Prepaid travel eSIM data plans for {target.name}. Instant QR delivery, no roaming fees.",
        "brand": {"@type": "Brand", "name": settings.SITE_NAME},
        "category": "Travel eSIM",
        "offers": {
            "@type": "AggregateOffer",
            "priceCurrency": "USD",
            "lowPrice": f"{min(p.price for p in plans):.2f}",
            "highPrice": f"{max(p.price for p in plans):.2f}",
            "offerCount": len(plans),
            "offers": offers,
        },
    }, ensure_ascii=False)
