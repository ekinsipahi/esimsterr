import json

from django.conf import settings


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

    return {
        "site_name": settings.SITE_NAME,
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
