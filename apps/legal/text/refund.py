"""Refund policy clauses."""
from django.utils.translation import gettext_noop as _

from apps.legal.blocks import Callout, P, UL
from apps.legal.registry import APP_SURFACES, Clause

CLAUSES = {c.id: c for c in [
    Clause("refund-lead", None, (
        P(_("eSIM plans are delivered instantly and digitally, so the rules are simple and "
            "we apply them consistently.")),
    )),

    Clause("full-refund", _("Full refund"), (
        P(_("You get your money back in full when:")),
        UL(
            _("the eSIM has **not been installed** on a device and has no usage, and you ask "
              "within **24 hours** of purchase; or"),
            _("we failed to deliver the profile (a provisioning error on our side); or"),
            _("the eSIM cannot connect at your destination and our support team cannot fix "
              "it — we check the line's own network log before deciding, so you do not have "
              "to prove anything."),
        ),
    )),

    Clause("no-refund", _("No refund"), (
        UL(
            _("The profile has been installed and has used data. An installed profile cannot "
              "be reissued or resold, so its cost is already spent."),
            _("The validity period expired with data unused. Unused days and gigabytes have "
              "no cash value."),
            _("Your device turned out to be locked to another carrier or does not support "
              "eSIM. Please check our [[url:compatible_devices|compatibility page]] before "
              "buying — ask us if you are unsure and we will confirm for your exact model."),
            _("You bought the wrong destination and had already installed the profile."),
            _("Loss caused by breach of our [[doc:acceptable-use|acceptable use policy]]."),
        ),
    )),

    Clause("refund-subscriptions", _("Subscriptions"), (
        P(_("A subscription is refunded on the same principles as a one-off plan, applied one "
            "billing period at a time. Cancel before a renewal and you are not charged for "
            "it: cancelling from your dashboard or the billing portal takes effect at the end "
            "of the period you are in, and no further payment is taken.")),
        P(_("A period that has already renewed and been delivered is not refundable once the "
            "data has been added to your line and used, in the same way an installed one-off "
            "plan is not. Cancelling mid-period does not produce a pro-rata refund; your data "
            "and days stay usable until the period ends.")),
        Callout(_("Two exceptions, applied without argument. If a renewal was charged and the "
                  "data was never added to your line, we refund that period in full. If you "
                  "cancelled and a renewal was taken anyway, we refund it in full — tell us "
                  "and we will not ask you to prove it.")),
        P(_("The first period of a subscription follows the ordinary rules above: uninstalled "
            "and unused within 24 hours, and it is refunded in full.")),
    )),

    Clause("refund-coupons", _("Orders with a discount code"), (
        P(_("A refund returns the amount you actually paid — the discounted total shown on "
            "your order, not the price before the discount. A discount code has no cash value "
            "of its own and is never refunded as money.")),
        P(_("Where a refund is partial, it is calculated from the amount paid. A code used on "
            "a refunded order is treated as spent and does not automatically become available "
            "again; if the refund was our fault, ask us and we will reissue it.")),
    )),

    Clause("refund-statutory", _("Your statutory rights, if you are in the EU"), (
        P(_("We sell from Estonia, so European consumer law applies to you wherever in the "
            "Union you are. That law gives you 14 days to withdraw from a distance "
            "contract — and lets you give that up for digital content delivered at once, "
            "which is what the tick box at checkout does.")),
        P(_("What is left after the tick is this policy, and it is more generous than the "
            "law requires: 24 hours to change your mind on an eSIM you have not installed, "
            "and a full refund whenever the fault is ours. Nothing here removes a right "
            "you have by law, and where the two differ the law wins.")),
    )),

    Clause("refund-how", _("How to request one"), (
        P(_("Email [[mail]] with your order reference (ES-XXXXXXX), or open a ticket from "
            "your dashboard. We answer within one business day and, when a refund is due, "
            "issue it to the original payment method.")),
    )),

    Clause("refund-app", _("Refunds for app users"), (
        P(_("Plans are bought on our website, not through the app store, so refunds come from "
            "us and not from Apple or Google. Asking the store will only send you back here, "
            "and slowly. Email [[mail]] with your order reference and we will handle it "
            "directly.")),
    ), surfaces=APP_SURFACES),

    Clause("refund-methods", _("Card and crypto refunds"), (
        P(_("Card refunds go back through Stripe and typically appear within 5-10 business "
            "days depending on your bank. Cryptocurrency refunds are sent to a wallet address "
            "you provide, in the same coin, at the amount received; network fees are "
            "deducted, and exchange-rate movement between payment and refund is not "
            "compensated.")),
    )),

    Clause("refund-partial", _("Partial refunds"), (
        P(_("If a plan worked for part of its period and then failed because of a network "
            "problem on our side, we refund pro rata for the unused days once support has "
            "confirmed the fault.")),
    )),

    Clause("chargebacks", _("Chargebacks"), (
        P(_("Please talk to us before opening a dispute — an email is faster than a "
            "chargeback, and we would rather fix the problem. Accounts used for chargeback "
            "abuse are suspended.")),
    )),
]}
