"""Acceptable use policy.

Split out of the terms because it is the document that has to be enforced most
often and changed most often: a new abuse pattern should be answerable by
editing one page with its own version history, not by reissuing the contract.
"""
from django.utils.translation import gettext_noop as _

from apps.legal.blocks import Callout, P, UL
from apps.legal.registry import Clause

CLAUSES = {c.id: c for c in [
    Clause("aup-lead", None, (
        P(_("This policy is part of the [[doc:terms|terms of service]]. It applies to every "
            "eSIM line we issue, and it exists for one reason: a line that is abused gets the "
            "whole IP range blocked by the local carrier, which breaks the service for every "
            "other traveller on it.")),
    )),

    Clause("aup-personal", _("Personal use"), (
        P(_("Plans are sold for your own use while travelling. You may use them on your "
            "phone, and share the connection with your own laptop or tablet by tethering.")),
        P(_("You may not resell the connection, operate it as a public hotspot or a "
            "commercial service, install it in permanently sited equipment such as CCTV, "
            "vending or IoT fleets, or run it as a proxy or VPN exit for other people. If you "
            "need connectivity at that scale, write to us — we would rather sell you the "
            "right product than cut you off.")),
    )),

    Clause("aup-fair-use", _("Fair use on unlimited plans"), (
        P(_("\"Unlimited\" means there is no data cap that stops you. It does not mean an "
            "unlimited claim on a shared radio network. Local carriers apply their own "
            "fair-use rules, and they may reduce speed after very heavy continuous use, "
            "particularly sustained tethering or overnight downloading.")),
        P(_("We do not apply a hidden cap of our own, and we do not bill overage. Where a "
            "specific destination is known to shape traffic after a certain volume, it is "
            "stated on that plan.")),
    )),

    Clause("aup-prohibited", _("What you must not do"), (
        UL(
            _("Anything unlawful where you are, where we are, or where the network is."),
            _("Sending spam or bulk unsolicited messages of any kind."),
            _("Port scanning, intrusion attempts, credential stuffing, denial-of-service "
              "traffic, or operating botnet or command-and-control infrastructure."),
            _("Distributing malware, phishing pages, or material that sexually exploits "
              "children."),
            _("Infringing copyright at scale."),
            _("Interfering with the mobile network: SIM boxing, grey-route voice or SMS "
              "termination, signalling abuse, or spoofing identifiers."),
            _("Sharing, selling or transferring an eSIM profile issued to you."),
            _("Evading a suspension by opening another account."),
        ),
    )),

    Clause("aup-enforcement", _("How we enforce it"), (
        P(_("We do not inspect your traffic, and we cannot see what you browse. What reaches "
            "us is an abuse report from a carrier or a third party, or a usage pattern that "
            "is not a person travelling. We act on those.")),
        P(_("Depending on severity we will contact you, suspend the line, close the account, "
            "or — where the law requires it or life is at risk — report it. A suspension for "
            "breach of this policy is not refunded. Where we have got it wrong, tell us and "
            "we will restore the line and apologise.")),
        Callout(_("Report abuse of our network to [[mail]] with the time, the destination and "
                  "any log excerpt you have. We answer abuse reports within one business day.")),
    )),
]}
