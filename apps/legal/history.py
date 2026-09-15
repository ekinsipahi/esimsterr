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
        "date": date(2026, 9, 15),
        "version": "2026.2",
        "documents": ("terms",),
        "material": False,
        "summary": _("Says plainly that discount codes apply to one-off plans and not to "
                     "subscriptions. This was already how it worked; it was not written "
                     "down anywhere a customer could read it."),
        "detail": (
            _("A percentage off a recurring charge comes off every renewal for as long as "
              "the subscription runs, which is not what a promotion is for. The "
              "subscription page now says so too, rather than simply not offering a "
              "field for a code."),
        ),
    },
    {
        "date": date(2026, 9, 15),
        "version": "2026.3",
        "documents": ("privacy",),
        "material": True,
        "summary": _("The app can now take payment directly instead of sending you to the "
                     "website, and can remember a card for next time. Saving a card is new "
                     "processing, so it is described."),
        "detail": (
            _("Added: what happens when you save a card. Stripe holds it; we hold an "
              "identifier for their customer record and never see the number. It is "
              "attached to your account, or to the app installation if you bought without "
              "one, which is why it follows you if you later register."),
            _("Added: removing a saved card removes it at Stripe rather than hiding it, and "
              "not saving is a tick box rather than a buried setting."),
        ),
    },
    {
        "date": date(2026, 9, 14),
        "version": "2026.2",
        "documents": ("privacy",),
        "material": True,
        "summary": _("The app gained three things that process data the previous policy did "
                     "not describe: a support ID generated on your device, gifting an eSIM "
                     "to someone else's email address, and referral codes."),
        "detail": (
            _("Added: the support ID — a random code generated on your device so you can "
              "quote it instead of spelling out an email address. It identifies the "
              "installation and not you, it is not an advertising identifier, and "
              "uninstalling the app ends it."),
            _("Added: what happens to a gift recipient's email address, which we process "
              "only to deliver and support the plan you bought them, and never add to a "
              "marketing list."),
            _("Added: what a referral records, and what your referrer is and is not told "
              "about you."),
            _("Added: the in-app inbox. Offers there follow the same marketing switch as "
              "email, so turning marketing off empties it of anything but service messages."),
        ),
    },
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
