"""What changed, when, and whether it mattered.

Hand-written on purpose. A diff can tell you a sentence moved; only a person can
say whether that sentence changed anyone's obligations, and that distinction is
what decides whether subscribers have to be emailed before the next renewal.
"""
from datetime import date

from django.utils.translation import gettext_noop as _

# Newest first.
HISTORY = (
    {
        "date": date(2026, 9, 13),
        "version": "2026.1",
        "documents": ("terms", "privacy", "refund", "acceptable-use", "cookies",
                      "subprocessors", "eula"),
        "material": True,
        "summary": _("First versioned release. The terms, privacy and refund policies were "
                     "split into separately versioned documents; the acceptable use rules, "
                     "the cookie list, the sub-processor register and the app licence were "
                     "published as documents of their own rather than paragraphs inside "
                     "another one."),
        "detail": (
            _("Added: an acceptable use policy, a cookie policy naming every cookie, a "
              "public register of sub-processors, and an end user licence agreement for the "
              "mobile app."),
            _("Added to the privacy policy: where data is transferred and under what "
              "safeguard, how we secure it, breach notification, a plain statement of "
              "children's age limits, and self-service account deletion."),
            _("Added to the terms: the statutory right of withdrawal and how it applies to "
              "digital content, suspension and termination, and governing law."),
            _("Corrected: the legal pages previously printed today's date as their last "
              "update, on every visit. Each document now carries a version and a real "
              "effective date."),
            _("Set throughout: the seller is Sterr Technologies OÜ, a private limited "
              "company registered in Estonia under code 17591465. Estonian law governs, "
              "the Harju County Court has jurisdiction, EU consumer law applies to every "
              "buyer in the Union, and the supervisory authority for data protection is "
              "the Estonian Data Protection Inspectorate."),
            _("Added: checkout and subscription now ask you to expressly request immediate "
              "delivery and acknowledge the effect on the 14-day withdrawal right, and "
              "your receipt repeats what you agreed to."),
        ),
    },
)
