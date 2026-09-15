"""Terms of service clauses."""
from django.utils.translation import gettext_noop as _

from apps.legal.blocks import Callout, P, UL
from apps.legal.registry import APP_SURFACES, WEB, Clause

CLAUSES = {c.id: c for c in [
    Clause("terms-lead", None, (
        P(_("These terms govern your use of {site} and the prepaid mobile data plans "
            "(\"eSIM plans\") sold through it. By buying or using a plan you accept them.")),
    )),

    Clause("what-we-sell", _("What we sell"), (
        P(_("We resell prepaid mobile data delivered as an eSIM profile. Plans are "
            "**data only**: they do not include GSM voice calls or SMS. You can make "
            "calls and send messages over the data connection using apps such as "
            "WhatsApp, FaceTime or Telegram.")),
        P(_("Coverage, available radio technology (4G/5G) and speed depend on the local "
            "carriers at your destination and on your device. We publish the partner "
            "operators for each destination, but we cannot guarantee a specific "
            "operator, a specific speed, or coverage in every location.")),
    )),

    Clause("validity", _("Validity and activation"), (
        P(_("A plan's validity period starts when the eSIM first connects to a mobile "
            "network in a covered country, not when you buy or install it. Once "
            "started, the period runs continuously in calendar days and cannot be "
            "paused. Unused data and unused days expire at the end of the period and "
            "are not refundable or transferable.")),
    )),

    Clause("your-device", _("Your device"), (
        P(_("You are responsible for checking that your device supports eSIM and is not "
            "locked to another carrier before buying. Our "
            "[[url:compatible_devices|compatibility page]] lists supported models. An "
            "eSIM profile can normally be installed on only one device and cannot be "
            "moved afterwards.")),
    )),

    Clause("prices-payment", _("Prices and payment"), (
        P(_("Prices are shown in US dollars and include our margin. Payment is taken at "
            "checkout by card (through Stripe) or in cryptocurrency (through "
            "NOWPayments). Crypto payments are credited at the amount actually "
            "received; if less than the invoice arrives, nothing is provisioned until "
            "the difference is paid or the payment is refunded.")),
        P(_("Where a plan shows a comparison figure next to the price, that figure is "
            "the going market rate charged elsewhere for equivalent wholesale data, not "
            "a previous price of ours. It is there so you can judge the saving, and it "
            "is not an offer by us at that amount.")),
    )),

    Clause("coupons", _("Coupons and promotional discounts"), (
        P(_("We sometimes issue discount codes. A code is valid only for what it says: "
            "it may be limited to certain plans, destinations or minimum order values, "
            "may expire, may be capped in total redemptions, and may be limited to one "
            "use per customer. The discount is applied at checkout and shown on the "
            "order before you pay; if no discount appears, the code did not apply and "
            "the full price stands.")),
        P(_("Discount codes apply to one-off plans only. They cannot be used on an "
            "auto-renewing subscription: a percentage off a recurring charge would come "
            "off every renewal indefinitely, which is not what a promotion is for.")),
        P(_("Codes have no cash value, cannot be exchanged for money, cannot be applied "
            "to an order that is already placed, and cannot normally be combined with "
            "another code. We may withdraw a code at any time, and we may cancel a "
            "discount or an order where a code has been obtained or used abusively, for "
            "example by creating accounts to reuse a one-per-customer offer.")),
    )),

    Clause("delivery", _("Delivery"), (
        P(_("eSIM profiles are delivered electronically, immediately after payment "
            "clears, to the email address you enter at checkout and to your account if "
            "you have one. It is your responsibility to enter a working email address. "
            "If a provisioning failure occurs on our side, we either deliver the plan or "
            "refund it in full.")),
    )),

    Clause("subscriptions", _("Auto-renewing subscriptions"), (
        P(_("Most plans are one-off purchases and nothing renews. Where a plan is "
            "offered as a subscription, this is stated clearly before you pay, and "
            "buying it starts a recurring payment. A subscription requires an account, "
            "because a recurring charge needs somewhere you can manage and stop it.")),
        P(_("A subscription renews automatically at the end of each billing period, at "
            "the interval shown when you subscribed, and charges the payment method "
            "held by our processor at the price shown for that plan. Each renewal tops "
            "up the same eSIM line, so you do not reinstall a profile. Your dashboard "
            "shows the renewal date before it happens.")),
        Callout(_("You can cancel at any time from your dashboard or from the billing "
                  "portal. Cancelling stops all future renewals; it does not refund the "
                  "period you are already in, and the data and days of that period "
                  "remain yours until they expire.")),
        P(_("If a renewal payment fails, the subscription is marked as needing attention "
            "and we may retry through our payment processor. If it cannot be collected, "
            "the subscription stops and no further data is added to the line. We may "
            "change subscription pricing, but only with notice before a renewal, and you "
            "can cancel before that renewal if you do not accept it.")),
    )),

    Clause("refunds-ref", _("Refunds and withdrawal"), (
        P(_("Refund terms are set out in our [[doc:refund|refund policy]], which forms "
            "part of these terms.")),
        P(_("As a consumer in the European Union you normally have 14 days to withdraw "
            "from a distance contract without giving a reason. An eSIM plan is digital "
            "content supplied immediately, and the law lets you give that up in exchange "
            "for getting it now.")),
        Callout(_("So checkout asks you to tick a box: you ask us to begin supply at once, "
                  "and you acknowledge that you lose the right of withdrawal once the "
                  "profile has been issued. Without that tick we cannot issue the eSIM "
                  "immediately. We keep a record of the tick and repeat it on your "
                  "receipt.")),
        P(_("Until the profile is issued, the withdrawal right is untouched. After it is "
            "issued but before you install it, our [[doc:refund|refund policy]] still "
            "gives you 24 hours to change your mind — more than the law leaves you.")),
    )),

    Clause("acceptable-use-ref", _("Acceptable use"), (
        P(_("How the connection may and may not be used is set out in our "
            "[[doc:acceptable-use|acceptable use policy]], which forms part of these "
            "terms. In short: normal personal use, no unlawful activity, no commercial "
            "resale of the connection, and no automated abuse of third parties.")),
        P(_("We may suspend a line that is being used in breach of that policy, without "
            "refund.")),
    )),

    Clause("assistant", _("The chat assistant"), (
        P(_("Signed-in customers can use an AI assistant for support questions. It "
            "answers from our documentation and from your own order and eSIM data, and "
            "it can hand the conversation to a human. It is a support tool, not advice: "
            "where an answer from the assistant conflicts with these terms, the refund "
            "policy or the plan details on the product page, those documents govern.")),
        P(_("Conversations are stored on your account, can be read by our support team, "
            "and are sent to our AI provider to generate replies. Do not paste "
            "passwords, full card numbers, recovery codes or identity documents into the "
            "chat — we will never ask for them. The [[doc:privacy|privacy policy]] "
            "explains how these conversations are handled. We may limit or withdraw "
            "access to the assistant if it is abused.")),
    )),

    # --- surface-specific: these appear only inside the mobile apps ----------
    Clause("app-licence", _("The mobile app"), (
        P(_("Your use of the {site} mobile app is also governed by our "
            "[[doc:eula|end user licence agreement]]. Where the licence and these terms "
            "differ on how the app itself may be used, the licence governs; on the plans "
            "you buy, these terms govern.")),
    ), surfaces=APP_SURFACES),

    Clause("app-purchases", _("Where purchases happen"), (
        P(_("Plans are sold on our website at {host}. The app is a way to see the "
            "catalogue, manage the eSIMs you already have, check your data use and reach "
            "support.")),
        P(_("A purchase made on the website is a contract between you and {company}. The "
            "operator of the app store you installed the app from is not a party to it, "
            "does not process the payment, and is not responsible for the plan, for "
            "support or for refunds. Ask us, not them.")),
    ), surfaces=APP_SURFACES),

    Clause("liability", _("Liability"), (
        P(_("We provide the connectivity service with reasonable care but do not warrant "
            "uninterrupted or error-free service. To the extent permitted by law our "
            "total liability for any claim relating to a plan is limited to the amount "
            "you paid for that plan. We are not liable for indirect or consequential "
            "loss, including missed bookings, lost work or data charges incurred on "
            "another network.")),
        P(_("Nothing in these terms limits liability that cannot be limited by law, "
            "including for death or personal injury caused by negligence, for fraud, or "
            "for the statutory rights of a consumer.")),
    )),

    Clause("accounts", _("Accounts"), (
        P(_("You may buy as a guest or create an account; a subscription requires an "
            "account. You must be old enough to enter a contract where you live, and at "
            "least 16. Keep your credentials safe; you are responsible for activity "
            "under your account. We may suspend accounts used fraudulently, including "
            "for payment fraud, coupon abuse or chargeback abuse.")),
        P(_("We record the IP address, browser user agent, browser language and "
            "referring page of each order for fraud prevention and to defend payment "
            "disputes, as described in the [[doc:privacy|privacy policy]].")),
        P(_("You can close your account at any time from your account page. Closing it "
            "cancels any active subscription, ends access to the dashboard and deletes "
            "your personal data except the records we are required to keep for "
            "accounting. eSIM lines already installed keep working until their validity "
            "ends.")),
    )),

    Clause("suspension", _("Suspension and termination"), (
        P(_("We may suspend or close an account, or stop a line, where there is fraud, "
            "a breach of the acceptable use policy, a chargeback raised without first "
            "contacting us, or a legal requirement to do so. Where the reason allows it "
            "we tell you what happened and what you can do about it.")),
        P(_("We may also stop selling a plan, a destination or the service as a whole. "
            "If we do, plans you have already bought run to the end of their validity, "
            "and anything paid for and not delivered is refunded.")),
    )),

    Clause("law", _("Governing law and disputes"), (
        P(_("These terms are governed by the law of {jurisdiction}, and the {courts} has "
            "jurisdiction. If you are a consumer resident elsewhere, this does not take "
            "away the protection of the mandatory consumer law of the country you live in, "
            "or your right to bring a claim in your local courts.")),
        P(_("As an Estonian company we are bound by European Union consumer law wherever "
            "in the Union you are buying from. If we cannot settle a complaint between us, "
            "you may take it to the Consumer Disputes Committee of the Estonian Consumer "
            "Protection and Technical Regulatory Authority, free of charge, at "
            "komisjon.ee — or to the equivalent body in your own country.")),
        P(_("Before any of that: email [[mail]]. Almost everything is a support problem "
            "with a same-day answer, and a dispute costs us both more than a refund does.")),
    )),

    Clause("changes", _("Changes"), (
        P(_("We may update these terms. Each version has a number and an effective date, "
            "shown at the top of this page, and earlier versions are listed on the "
            "[[url:legal_changes|change history page]].")),
        P(_("The version in force is the one published when you buy. For a subscription, "
            "it is the one published when the current period began, and a material "
            "change is notified by email before the next renewal, so you can cancel "
            "before it takes effect if you do not accept it.")),
    )),

    Clause("contact", _("Who you are buying from"), (
        P(_("{company}, trading as {site}, a private limited company registered in Estonia "
            "under registry code {registration}.")),
        UL(
            _("Registered address: {address}"),
            _("Email: {support} — we answer within one business day"),
            _("Website: {host}"),
        ),
        P(_("We are entered in the Estonian commercial register held by the registration "
            "department of Tartu County Court, and the company is represented by its "
            "management board.")),
    )),
]}
