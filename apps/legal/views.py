from django.conf import settings
from django.http import Http404
from django.shortcuts import render
from django.utils.translation import gettext as _

from apps.legal.documents import (
    BY_SLUG, DOCUMENTS, document_url, has_app, listed_documents, render as render_doc,
    stamp, version_hash,
)
from apps.legal.history import HISTORY
from apps.legal.registry import ALL_SURFACES, WEB


def _surface(request) -> str:
    """Which surface to compose for.

    Staff can preview the app wording in a browser, which is how you check the
    store-specific clauses without building an app. Everyone else gets the web
    composition, so the public page can never be a different document from the
    one the search engine indexed.
    """
    wanted = request.GET.get("surface")
    if wanted in ALL_SURFACES and request.user.is_authenticated and request.user.is_staff:
        return wanted
    return WEB


def document(request, slug):
    doc = BY_SLUG.get(slug)
    if doc is None:
        raise Http404
    surface = _surface(request)
    if not doc.applies_to(surface):
        raise Http404
    return render(request, "legal/document.html", {
        "doc": doc,
        "clauses": render_doc(doc, surface),
        "surface": surface,
        "stamp": stamp(doc, surface),
        "others": [d for d in listed_documents() if d.slug != doc.slug],
        "seo_title": f"{_(doc.seo_title or doc.title)} — {settings.SITE_NAME}",
        "seo_description": _(doc.summary),
    })


def index(request):
    docs = listed_documents()
    return render(request, "legal/index.html", {
        "docs": [(d, document_url(d), stamp(d)) for d in docs],
        "unlisted": [] if has_app() else [d for d in DOCUMENTS if not d.listed],
        "history": HISTORY[:1],
        "seo_title": _("Legal — %(site)s") % {"site": settings.SITE_NAME},
        "seo_description": _("Terms, privacy, refunds, acceptable use, cookies and the "
                             "companies that process data for us — each with its own version "
                             "and effective date."),
    })


def changes(request):
    entries = [
        {**entry, "docs": [BY_SLUG[s] for s in entry["documents"] if s in BY_SLUG]}
        for entry in HISTORY
    ]
    return render(request, "legal/changes.html", {
        "history": entries,
        "seo_title": _("Legal change history — %(site)s") % {"site": settings.SITE_NAME},
        "seo_description": _("Every version of our terms and policies, when it took effect, "
                             "and what changed."),
    })
