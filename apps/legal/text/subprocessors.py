"""The sub-processor register.

Published as its own document on purpose. The GDPR expects a controller to be
able to say who else touches the data, and a provider swap is a routine
operational change -- it should be a one-line edit with its own version bump,
not a reason to reissue the privacy policy and invalidate every acceptance
record attached to it.
"""
from django.utils.translation import gettext_noop as _

from apps.legal.blocks import Callout, P, Table
from apps.legal.registry import Clause

CLAUSES = {c.id: c for c in [
    Clause("subp-lead", None, (
        P(_("These are the companies that process personal data on our behalf so that {site} "
            "can work. Each one is under a contract limiting it to the purpose listed, and "
            "each transfer outside the European Economic Area is covered by the European "
            "Commission's standard contractual clauses or by an adequacy decision.")),
    )),

    Clause("subp-list", _("Current sub-processors"), (
        Table(
            (_("Provider"), _("What it does"), _("What it receives"), _("Region")),
            [
                ("Yesim", _("Issues and manages the eSIM profile"),
                 _("Your email address and the plan bought"), _("European Union")),
                ("Stripe", _("Card payments, subscriptions and refunds"),
                 _("Email, amount, card data you enter on Stripe's own form"),
                 _("European Union and United States")),
                ("NOWPayments", _("Cryptocurrency invoices"),
                 _("Order reference, amount, wallet transaction"), _("European Union")),
                ("Supabase", _("The database the service runs on"),
                 _("All account, order and support records"), _("European Union (Frankfurt)")),
                ("Render", _("Application hosting"),
                 _("Anything in a request, in transit"), _("European Union (Frankfurt)")),
                ("Cloudflare", _("DNS, TLS and protection against attack"),
                 _("IP address and request metadata"), _("Global edge network")),
                ("Resend", _("Delivers order, support and account email"),
                 _("Email address and message content"), _("United States")),
                ("Anthropic", _("Generates chat assistant replies"),
                 _("The conversation, and the order context it needs"), _("United States")),
                ("Sentry", _("Error monitoring"),
                 _("Technical error data; user identifiers are stripped"), _("European Union")),
                ("Google", _("Sign-in with Google, and analytics where enabled"),
                 _("Email and name for sign-in; anonymised usage data for analytics"),
                 _("European Union and United States")),
            ],
        ),
        Callout(_("Under Anthropic's commercial terms, assistant conversations are not used "
                  "to train their models.")),
    )),

    Clause("subp-changes", _("Changes to this list"), (
        P(_("When a provider is added or replaced, this page is updated and its version "
            "number changes before the new provider starts processing. The "
            "[[url:legal_changes|change history]] shows when each version took effect, so you "
            "can always see who was involved at the time of your own order.")),
        P(_("If you object to a new sub-processor, tell us at [[mail]]. In practice the only "
            "remedy for a service like this one is to stop using it and ask for deletion, and "
            "we will not make that difficult.")),
    )),
]}
