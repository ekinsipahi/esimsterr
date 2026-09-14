"""The document registry: what exists, what it is made of, and which version.

Adding a document is three lines here plus a text module. Changing where a
clause appears is one word. That is the whole point of the split: the legal
surface of the business is a configuration, not a pile of templates that have to
be edited in parallel and inevitably fall out of step.

Versions are dotted year.release. Bump the minor part for a correction that does
not change anyone's obligations, and the year-release part for a change that
does — a material change is what triggers notice to subscribers, so the two must
be told apart deliberately rather than inferred from a diff.
"""
from __future__ import annotations

from datetime import date
from functools import lru_cache

from django.conf import settings
from django.urls import NoReverseMatch, reverse
from django.utils.translation import gettext_noop as _

from apps.legal.registry import (
    ALL_SURFACES, ANDROID, APP_SURFACES, IOS, WEB, Document, content_hash,
    numbered, resolve,
)
from apps.legal.text import aup, cookies, eula, privacy, refund, subprocessors, terms

# One flat namespace, so a clause can be shared between documents. Duplicate ids
# across modules are a mistake we want to hear about at import time.
CLAUSES: dict = {}
for _module in (terms, privacy, refund, aup, cookies, subprocessors, eula):
    _clash = CLAUSES.keys() & _module.CLAUSES.keys()
    if _clash:
        raise RuntimeError(f"duplicate legal clause id(s): {sorted(_clash)}")
    CLAUSES.update(_module.CLAUSES)


DOCUMENTS: tuple = (
    Document(
        slug="terms",
        url_name="terms",
        title=_("Terms of Service"),
        summary=_("What you are buying, how it is delivered, and what happens when something "
                  "goes wrong."),
        seo_title=_("Terms of Service"),
        version="2026.1",
        effective=date(2026, 9, 13),
        clauses=(
            "terms-lead", "what-we-sell", "validity", "your-device", "prices-payment",
            "coupons", "delivery", "subscriptions", "refunds-ref", "acceptable-use-ref",
            "assistant", "app-licence", "app-purchases", "liability", "accounts",
            "suspension", "law", "changes", "contact",
        ),
    ),
    Document(
        slug="privacy",
        url_name="privacy",
        title=_("Privacy Policy"),
        summary=_("What we collect, why, how long we keep it, and the things we never touch."),
        seo_title=_("Privacy Policy"),
        version="2026.3",
        effective=date(2026, 9, 15),
        numbered=False,
        clauses=(
            "privacy-lead", "collect", "never-collect", "app-data", "fraud",
            "cards", "gifts", "messages", "coupons-data",
            "subscriptions-data", "assistant-data", "why", "sharing", "transfers",
            "cookies-ref", "retention", "security", "rights", "deletion", "children",
            "privacy-changes",
        ),
    ),
    Document(
        slug="refund",
        url_name="refund",
        title=_("Refund Policy"),
        summary=_("When you get your money back, when you do not, and how to ask."),
        seo_title=_("Refund Policy"),
        version="2026.1",
        effective=date(2026, 9, 13),
        numbered=False,
        clauses=(
            "refund-lead", "full-refund", "no-refund", "refund-subscriptions",
            "refund-coupons", "refund-statutory", "refund-how", "refund-app",
            "refund-methods", "refund-partial", "chargebacks",
        ),
    ),
    Document(
        slug="acceptable-use",
        url_name="acceptable_use",
        title=_("Acceptable Use Policy"),
        summary=_("What the connection is for, what it is not for, and how a breach is handled."),
        seo_title=_("Acceptable Use Policy"),
        version="2026.1",
        effective=date(2026, 9, 13),
        numbered=False,
        clauses=("aup-lead", "aup-personal", "aup-fair-use", "aup-prohibited", "aup-enforcement"),
    ),
    Document(
        slug="cookies",
        url_name="cookies",
        title=_("Cookie Policy"),
        summary=_("Every cookie we set, what it does, and how to switch it off."),
        seo_title=_("Cookie Policy"),
        version="2026.1",
        effective=date(2026, 9, 13),
        numbered=False,
        clauses=("cookies-lead", "cookies-list", "cookies-analytics", "cookies-control",
                 "cookies-app", "cookies-contact"),
    ),
    Document(
        slug="subprocessors",
        url_name="subprocessors",
        title=_("Sub-processors"),
        summary=_("Every company that processes data on our behalf, what it gets, and where it is."),
        seo_title=_("Sub-processors"),
        version="2026.1",
        effective=date(2026, 9, 13),
        numbered=False,
        clauses=("subp-lead", "subp-list", "subp-changes"),
    ),
    Document(
        slug="eula",
        url_name="eula",
        title=_("App Licence"),
        summary=_("The licence for the mobile app itself, separate from what you buy through us."),
        seo_title=_("End User Licence Agreement"),
        version="2026.1",
        effective=date(2026, 9, 13),
        numbered=True,
        # Published from day one so a store reviewer has a URL to open, but kept
        # out of the footer until an app actually exists.
        listed=False,
        clauses=(
            "eula-lead", "eula-licence", "eula-purchases", "eula-support", "eula-warranty",
            "eula-claims", "eula-apple", "eula-google", "eula-legal", "eula-termination",
            "eula-contact",
        ),
    ),
)

BY_SLUG = {d.slug: d for d in DOCUMENTS}

# The documents a customer is taken to have accepted when they buy or register.
# Acceptance is recorded against these, with their versions, so "what did they
# agree to" has an answer that does not depend on what the page says today.
CONTRACT_DOCUMENTS = ("terms", "privacy", "refund", "acceptable-use")


def get_document(slug: str | None):
    return BY_SLUG.get(slug or "")


def document_url(doc) -> str:
    if doc.url_name:
        try:
            return reverse(doc.url_name)
        except NoReverseMatch:
            pass
    return f"/legal/{doc.slug}/"


def has_app() -> bool:
    """Whether a mobile app is live, which is what decides if app-only documents
    are advertised. Driven by the store URLs, so shipping the app is a settings
    change rather than a code change."""
    return bool(settings.APP_STORE_URL or settings.PLAY_STORE_URL)


def listed_documents(surface: str = WEB) -> list:
    out = [d for d in DOCUMENTS if d.applies_to(surface) and d.listed]
    if has_app():
        out += [d for d in DOCUMENTS if d.applies_to(surface) and not d.listed]
    return out


def render(doc, surface: str = WEB) -> list:
    return numbered(doc, resolve(doc, CLAUSES, surface))


@lru_cache(maxsize=None)
def version_hash(slug: str, surface: str = WEB) -> str:
    return content_hash(BY_SLUG[slug], CLAUSES, surface)


def stamp(doc, surface: str = WEB) -> str:
    """The identifier stored in an acceptance record: version plus content hash.

    The version alone would let a document be edited without the record noticing;
    the hash alone would be unreadable to a human reading a support ticket."""
    return f"{doc.version}+{version_hash(doc.slug, surface)}"


def contract_stamps(surface: str = WEB) -> dict:
    return {slug: stamp(BY_SLUG[slug], surface) for slug in CONTRACT_DOCUMENTS}
