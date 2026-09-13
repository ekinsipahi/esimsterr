"""End user licence agreement for the mobile apps.

Apple does not require a custom EULA -- an app with none falls under Apple's own
standard licence. But an app that links to its own terms, as ours does, must
carry at least the ten points Apple sets out as minimum terms, and the Apple-only
ones (Apple is not a party, Apple is a third-party beneficiary, Apple's sole
warranty remedy is a refund of the purchase price) are the clauses reviewers
actually look for. They are marked as iOS-only here, because printing them in an
Android build would be nonsense and printing Google's equivalents on iOS would be
too.

This document is listed but unlinked from the footer until an app ships; set
APP_STORE_URL or PLAY_STORE_URL and it appears.
"""
from django.utils.translation import gettext_noop as _

from apps.legal.blocks import P, UL
from apps.legal.registry import ANDROID, APP_SURFACES, IOS, WEB, Clause

# The EULA is readable on the web too -- a store reviewer needs a public URL for
# it -- so the general clauses carry all three surfaces.
ALL = (WEB, IOS, ANDROID)

CLAUSES = {c.id: c for c in [
    Clause("eula-lead", None, (
        P(_("This licence covers the {site} mobile app itself. What you buy through us is "
            "covered by the [[doc:terms|terms of service]]; how your data is handled is in "
            "the [[doc:privacy|privacy policy]]. This agreement is between you and {company} "
            "alone.")),
    ), surfaces=ALL),

    Clause("eula-licence", _("Your licence"), (
        P(_("We grant you a personal, non-exclusive, non-transferable, revocable licence to "
            "install and use the app on devices you own or control, for your own use, in "
            "accordance with the usage rules of the store you installed it from. The app is "
            "licensed to you, not sold.")),
        P(_("You may not copy, rent, lease, sell, sublicense or redistribute the app, "
            "reverse-engineer or decompile it except to the extent the law expressly permits, "
            "remove any notice of ownership from it, or use it to build a competing service.")),
    ), surfaces=ALL),

    Clause("eula-purchases", _("Purchases are made on the website"), (
        P(_("The app does not sell anything. eSIM plans are bought on {host}, in your own "
            "browser, and the app opens that page rather than collecting payment itself. "
            "Everything you buy is a contract with {company}.")),
        P(_("This is a deliberate design, not a limitation: connectivity is a service "
            "consumed outside the app, so it is sold outside the app.")),
    ), surfaces=ALL),

    Clause("eula-support", _("Maintenance and support"), (
        P(_("{company} is solely responsible for maintaining and supporting the app. The "
            "store you installed it from has no obligation to provide any support or "
            "maintenance for it. Ask us: [[mail]].")),
    ), surfaces=ALL),

    Clause("eula-warranty", _("Warranty"), (
        P(_("The app is provided as it is. To the extent the law permits, we disclaim all "
            "warranties, express or implied, including fitness for a particular purpose. "
            "Nothing here limits the statutory rights you have as a consumer.")),
        P(_("If the app fails to conform to any warranty that does apply, you may notify "
            "Apple, and Apple will refund the purchase price of the app to you — which, as "
            "the app is free, is nothing. To the maximum extent permitted by law, Apple has "
            "no other warranty obligation whatsoever with respect to the app. Any other "
            "claim, loss, liability, damage, cost or expense attributable to a failure to "
            "conform to a warranty is our responsibility.")),
    ), surfaces=ALL),

    Clause("eula-claims", _("Claims and intellectual property"), (
        P(_("{company}, not the app store operator, is responsible for addressing any claim "
            "by you or a third party relating to the app or your possession and use of it, "
            "including product liability claims, any claim that the app fails to conform to a "
            "legal or regulatory requirement, and claims arising under consumer protection, "
            "privacy or similar legislation.")),
        P(_("If a third party claims that the app infringes their intellectual property "
            "rights, {company} is solely responsible for the investigation, defence, "
            "settlement and discharge of that claim.")),
    ), surfaces=ALL),

    Clause("eula-apple", _("Apple"), (
        P(_("This licence is concluded between you and {company} only, and not with Apple. "
            "Apple is not responsible for the app or its content. Apple has no obligation "
            "to furnish any maintenance or support services for it.")),
        P(_("Apple and Apple's subsidiaries are third-party beneficiaries of this licence, "
            "and on your acceptance of it Apple will have the right — and is deemed to have "
            "accepted the right — to enforce it against you as a third-party beneficiary.")),
        P(_("Your use of the app must comply with the Usage Rules in Apple's App Store Terms "
            "of Service, which are part of your agreement with Apple, not with us.")),
    ), surfaces=(WEB, IOS)),

    Clause("eula-google", _("Google Play"), (
        P(_("Where you installed the app from Google Play, your use is also subject to the "
            "Google Play Terms of Service. Google is not a party to this licence and is not "
            "responsible for the app, its content or its support.")),
    ), surfaces=(WEB, ANDROID)),

    Clause("eula-legal", _("Legal compliance"), (
        P(_("By using the app you confirm that you are not located in a country subject to a "
            "government embargo, or designated as a terrorist-supporting country, and that "
            "you are not listed on any government list of prohibited or restricted parties.")),
        P(_("You must also comply with the terms of any third-party agreement that applies to "
            "your use of the app, including your mobile network's data plan.")),
    ), surfaces=ALL),

    Clause("eula-termination", _("Termination"), (
        P(_("This licence ends if you delete the app, close your account, or breach these "
            "terms. Ending it does not affect eSIM plans you have already bought: those run "
            "to the end of their validity and remain governed by the "
            "[[doc:terms|terms of service]].")),
    ), surfaces=ALL),

    Clause("eula-contact", _("Who we are"), (
        P(_("{company}, trading as {site}. Questions, complaints and claims about the app go "
            "to [[mail]]. We answer within one business day.")),
    ), surfaces=ALL),
]}
