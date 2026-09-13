import json

from django.conf import settings
from django.urls import translate_url
from django.utils import translation


def site(request):
    """Site-wide template context: SEO defaults, canonical URL, Organization JSON-LD."""
    try:
        canonical = request.build_absolute_uri(request.path)
        if settings.CANONICAL_HOST and not settings.DEBUG:
            canonical = f"https://{settings.CANONICAL_HOST}{request.path}"
    except Exception:  # noqa: BLE001
        canonical = ""

    site_url = settings.SITE_URL
    org = {
        "@context": "https://schema.org",
        "@type": "Organization",
        "@id": f"{site_url}/#org",
        "name": settings.SITE_NAME,
        "legalName": settings.COMPANY_LEGAL_NAME,
        "url": site_url,
        "logo": {"@type": "ImageObject", "url": f"{site_url}/static/img/logo.png"},
        "contactPoint": {
            "@type": "ContactPoint",
            "contactType": "customer support",
            "email": settings.SUPPORT_EMAIL,
            "availableLanguage": ["en"],
        },
    }
    if settings.SITE_SAMEAS:
        org["sameAs"] = settings.SITE_SAMEAS

    # hreflang alternates. Only languages actually enabled are advertised, so a
    # half-translated locale never gets pointed at by a live page.
    lang = translation.get_language() or settings.LANGUAGE_CODE
    hreflangs = []
    if len(settings.LANGUAGES) > 1 and canonical:
        for code, _name in settings.LANGUAGES:
            try:
                hreflangs.append((code, translate_url(canonical, code)))
            except Exception:  # noqa: BLE001
                continue

    # sign_up and login both end in a redirect, so the event has to survive one
    # hop. Popping it here means it fires on the next page and never again.
    session_events = []
    if settings.GA_MEASUREMENT_ID and hasattr(request, "session"):
        session_events = request.session.pop("pending_analytics", []) or []

    return {
        "session_analytics_events": session_events,
        "site_name": settings.SITE_NAME,
        "site_tagline": "Connect without borders.",
        "company_legal_name": settings.COMPANY_LEGAL_NAME,
        # Legal documents must show the date they were last revised, not today's
        # date. Bump LEGAL_UPDATED in settings when a policy actually changes.
        "legal_updated": settings.LEGAL_UPDATED,
        "current_language": lang,
        "available_languages": settings.LANGUAGES,
        "hreflangs": hreflangs,
        "is_rtl": lang.split("-")[0] in settings.RTL_LANGUAGES,
        "subscriptions_enabled": settings.SUBSCRIPTIONS_ENABLED and bool(settings.STRIPE_SECRET_KEY),
        "assistant_enabled": settings.ASSISTANT_ENABLED,
        "site_url": site_url,
        "support_email": settings.SUPPORT_EMAIL,
        "default_description": settings.DEFAULT_DESCRIPTION,
        "canonical_url": canonical,
        "org_schema_json": json.dumps(org, ensure_ascii=False),
        "GA_MEASUREMENT_ID": settings.GA_MEASUREMENT_ID,
        "GOOGLE_CLIENT_ID": settings.GOOGLE_CLIENT_ID,
        "app_store_url": settings.APP_STORE_URL,
        "play_store_url": settings.PLAY_STORE_URL,
        "stripe_enabled": bool(settings.STRIPE_SECRET_KEY),
        "crypto_enabled": bool(settings.NOWPAYMENTS_API_KEY),
    }
