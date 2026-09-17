"""Structured data, built in one place.

WHY ONE PLACE. There were three copies of the FAQ builder in three apps and a
fourth idea of how to make an absolute URL. Structured data is a set of claims a
search engine will act on, and claims that disagree with each other are worse
than no claims: a page that publishes itself under one address and links to
another looks like two pages, and the duplicate is the one that ranks.

WHY IT MATTERS HERE. Everything sold on this site is bought by someone comparing
prices in a search result. A plan page that says what it is, what it costs and
who is selling it gets the price and the range shown in the result itself; one
that does not is a blue link next to competitors who did the work.

Everything here returns plain data. Rendering is the caller's problem, and
`dumps` is the only place that decides how it is serialised.
"""
from __future__ import annotations

import json

from django.conf import settings

# Every page names the same organisation by reference rather than repeating it.
# One node, described once in the site-wide graph, pointed at from everywhere
# else -- which is what tells a crawler the seller on a plan page and the
# publisher of a blog post are the same company.
ORG_ID = f"{settings.SITE_URL.rstrip('/')}/#org"
SITE_ID = f"{settings.SITE_URL.rstrip('/')}/#website"


def dumps(payload) -> str:
    """JSON for a <script type="application/ld+json"> block."""
    if not payload:
        return ""
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


def absolute(request, path: str) -> str:
    """The canonical address of a path.

    Built the way core.context_processors.site builds the canonical link, so a
    page served on an allowed alias host does not publish itself under a second
    address in its own markup.
    """
    if not path:
        return ""
    if path.startswith("http"):
        return path
    if settings.CANONICAL_HOST and not settings.DEBUG:
        return f"https://{settings.CANONICAL_HOST}{path}"
    return request.build_absolute_uri(path) if request is not None else path


# --- the site itself ---------------------------------------------------------
def website() -> dict:
    """WebSite, with the search action that produces a sitelinks search box.

    Pointed at the destination search because that is the search a visitor
    actually wants: they know where they are going, not which plan they want.
    """
    site_url = settings.SITE_URL.rstrip("/")
    return {
        "@context": "https://schema.org",
        "@type": "WebSite",
        "@id": SITE_ID,
        "name": settings.SITE_NAME,
        "url": f"{site_url}/",
        "publisher": {"@id": ORG_ID},
        "inLanguage": settings.LANGUAGE_CODE,
        "potentialAction": {
            "@type": "SearchAction",
            "target": {
                "@type": "EntryPoint",
                "urlTemplate": f"{site_url}/destinations/?q={{search_term_string}}",
            },
            "query-input": "required name=search_term_string",
        },
    }


# --- pages -------------------------------------------------------------------
def faq(items) -> dict | None:
    """FAQPage from (question, answer) pairs.

    str() on both because half the callers pass lazily translated strings, which
    json.dumps cannot serialise and which fail at render rather than at import.
    """
    pairs = [(str(q), str(a)) for q, a in (items or []) if q and a]
    if not pairs:
        return None
    return {
        "@context": "https://schema.org",
        "@type": "FAQPage",
        "mainEntity": [
            {"@type": "Question", "name": q,
             "acceptedAnswer": {"@type": "Answer", "text": a}}
            for q, a in pairs
        ],
    }


def breadcrumbs(request, crumbs) -> dict | None:
    """BreadcrumbList from the trail the page already renders.

    A crumb with no URL is a section label with no page behind it. schema.org
    wants an `item` on every entry except the last, so those are dropped here
    and the rest renumbered; they stay in the visible trail, where they are
    useful to a reader even without a link.
    """
    crumbs = list(crumbs or [])
    if len(crumbs) < 2:
        return None
    listed = [(label, url) for label, url in crumbs[:-1] if url] + crumbs[-1:]
    items = []
    for position, (label, url) in enumerate(listed, start=1):
        entry = {"@type": "ListItem", "position": position, "name": str(label)}
        if url:
            entry["item"] = absolute(request, url)
        items.append(entry)
    return {"@context": "https://schema.org", "@type": "BreadcrumbList",
            "itemListElement": items}


def product(request, *, name: str, description: str, plans, url: str = "",
            area: str = "") -> dict | None:
    """Product with an AggregateOffer over the plans on the page.

    The aggregate is what puts a "from $1.49" in the search result, and the
    individual offers are what let it be trusted: a low price with nothing
    behind it is the shape of a scraped listing.

    Prices are formatted rather than passed as Decimal because json.dumps cannot
    serialise Decimal, and float would reintroduce the rounding this codebase
    keeps money in strings to avoid.
    """
    priced = [p for p in (plans or []) if p.price is not None]
    if not priced:
        return None
    offers = [{
        "@type": "Offer",
        "name": p.title,
        "price": f"{p.price:.2f}",
        "priceCurrency": "USD",
        "availability": "https://schema.org/InStock",
        "url": absolute(request, p.get_absolute_url()),
        "seller": {"@id": ORG_ID},
    } for p in priced[:30]]

    payload = {
        "@context": "https://schema.org",
        "@type": "Product",
        "name": name,
        "description": description,
        "category": "Travel eSIM",
        "brand": {"@id": ORG_ID},
        "offers": {
            "@type": "AggregateOffer",
            "priceCurrency": "USD",
            "lowPrice": f"{min(p.price for p in priced):.2f}",
            "highPrice": f"{max(p.price for p in priced):.2f}",
            "offerCount": len(priced),
            "offers": offers,
        },
    }
    if url:
        payload["url"] = absolute(request, url)
    if area:
        payload["areaServed"] = {"@type": "Place", "name": area}
    return payload


def article(request, post) -> dict:
    """Article for a blog post, published by the organisation rather than by a
    bare name -- the same node the rest of the site points at."""
    url = absolute(request, post.get_absolute_url())
    payload = {
        "@context": "https://schema.org",
        "@type": "Article",
        "headline": post.title,
        "description": (post.seo_description or post.excerpt or "")[:300],
        "mainEntityOfPage": {"@type": "WebPage", "@id": url},
        "url": url,
        "publisher": {"@id": ORG_ID},
        "author": {"@id": ORG_ID},
        "isAccessibleForFree": True,
    }
    published = getattr(post, "published_at", None) or getattr(post, "created_at", None)
    if published:
        payload["datePublished"] = published.isoformat()
    updated = getattr(post, "updated_at", None)
    if updated:
        payload["dateModified"] = updated.isoformat()
    image = getattr(post, "cover_url", "") or getattr(post, "image_url", "")
    if image:
        payload["image"] = absolute(request, image)
    return payload
