"""Legal routes.

The three original paths keep their exact URLs and view names. They are indexed,
they are in the sitemap, and they are linked from the footer of every page and
from old order emails; a tidier /legal/terms/ would be a self-inflicted 404
across all of it.
"""
from django.urls import path

from . import views

urlpatterns = [
    path("legal/", views.index, name="legal_index"),
    path("legal/changes/", views.changes, name="legal_changes"),
    # Original URLs, unchanged.
    path("terms/", views.document, {"slug": "terms"}, name="terms"),
    path("privacy/", views.document, {"slug": "privacy"}, name="privacy"),
    path("refund-policy/", views.document, {"slug": "refund"}, name="refund"),
    # New documents.
    path("acceptable-use/", views.document, {"slug": "acceptable-use"}, name="acceptable_use"),
    path("cookie-policy/", views.document, {"slug": "cookies"}, name="cookies"),
    path("sub-processors/", views.document, {"slug": "subprocessors"}, name="subprocessors"),
    path("app-licence/", views.document, {"slug": "eula"}, name="eula"),
]
