"""Cookie policy.

A separate document because the cookie table changes on a different schedule
from the privacy policy: adding one measurement tool should not force a reissue
of the document that describes lawful bases.
"""
from django.utils.translation import gettext_noop as _

from apps.legal.blocks import Callout, P, Table, UL
from apps.legal.registry import APP_SURFACES, Clause, WEB

CLAUSES = {c.id: c for c in [
    Clause("cookies-lead", None, (
        P(_("We use as few cookies as a shop can. There is no advertising cookie, no "
            "third-party tracker following you off the site, and nothing that needs a banner "
            "covering half the page before you can read it.")),
    )),

    Clause("cookies-list", _("What is actually set"), (
        Table(
            (_("Name"), _("Purpose"), _("Type"), _("Expires")),
            [
                ("sessionid", _("Keeps you signed in, and remembers a guest order between the "
                                "checkout and the confirmation page."),
                 _("Strictly necessary"), _("2 weeks, or when you sign out")),
                ("csrftoken", _("Proves a form was submitted from our own page. Without it, "
                                "forms cannot be accepted at all."),
                 _("Strictly necessary"), _("1 year")),
                ("esimsterr_lang", _("Remembers the language you chose, so you are not sent "
                                     "back to English on the next page."),
                 _("Strictly necessary"), _("1 year")),
                ("_ga, _ga_*", _("Google Analytics: counts visits and measures which pages "
                                 "lead to a sale. Set only when analytics is enabled."),
                 _("Analytics"), _("13 months")),
            ],
        ),
        P(_("Your light or dark theme preference is **not** a cookie. It is kept in your "
            "browser's local storage and is never sent to our server.")),
    ), surfaces=(WEB,)),

    Clause("cookies-analytics", _("How analytics is configured"), (
        P(_("Where analytics is enabled it runs with advertising signals switched off: ad "
            "storage, ad user data and ad personalisation are all denied before the first "
            "request, and IP anonymisation is on. It measures pages, searches and purchases "
            "so we know which destinations sell. It does not build an advertising profile, "
            "and the data is not shared with advertisers.")),
        P(_("If we ever start advertising, that is the point at which a consent banner "
            "appears — turning the signals on quietly is exactly what makes a site "
            "non-compliant.")),
    )),

    Clause("cookies-control", _("Turning them off"), (
        P(_("Every browser can block or delete cookies, usually under Settings, Privacy. "
            "Blocking the strictly necessary ones will stop you signing in and stop checkout "
            "working, because the site then cannot tell one request from another.")),
        UL(
            _("To opt out of Google Analytics everywhere, install Google's own browser "
              "add-on, or use your browser's tracking protection."),
            _("Deleting cookies here does not affect an eSIM you have already installed."),
        ),
    ), surfaces=(WEB,)),

    Clause("cookies-app", _("In the mobile app"), (
        P(_("The app does not use cookies. It stores a sign-in token and your display "
            "preferences on the device itself, and erases the token when you sign out. It "
            "contains no advertising SDK and no cross-app tracking, so it never asks for "
            "permission to track you.")),
    ), surfaces=APP_SURFACES),

    Clause("cookies-contact", _("Questions"), (
        P(_("The wider picture is in the [[doc:privacy|privacy policy]]. Anything else: "
            "[[mail]].")),
    )),
]}
