"""Privacy policy clauses.

The app-surface clauses here are not decoration. Apple's privacy "nutrition
label" and Google Play's Data safety form are both declarations that must match
this document; when they disagree, the store is the one that notices. Keeping
the app disclosures inside the same clause library as the web ones is what stops
the two drifting apart.
"""
from django.utils.translation import gettext_noop as _

from apps.legal.blocks import Callout, P, Table, UL
from apps.legal.registry import APP_SURFACES, Clause

CLAUSES = {c.id: c for c in [
    Clause("privacy-lead", None, (
        P(_("This policy explains what {site} collects, why, and what we never touch. "
            "The short version: we need an email address to deliver an eSIM, we keep "
            "enough of a record to defend a payment dispute, and we do not look at your "
            "traffic.")),
        P(_("{company} (registry code {registration}, {address}) is the data controller "
            "for everything described here. We are established in Estonia, so this policy "
            "is written to the General Data Protection Regulation and the Estonian "
            "Personal Data Protection Act. For anything about your data, write to "
            "[[mail]].")),
    )),

    Clause("collect", _("What we collect"), (
        UL(
            _("**Your email address.** Required — it is how the QR code and receipt reach you."),
            _("**Order records.** Which plan you bought, when, the subtotal, any discount "
              "applied, the amount actually charged, and the reference from the payment provider."),
            _("**eSIM technical data.** The ICCID we issued you, its activation status, the "
              "data counter the network reports, and the radio technology last seen. This "
              "comes from our connectivity partner, not from your device."),
            _("**Request details attached to an order.** The IP address the order was placed "
              "from, the browser user agent, the browser language and the referring page. "
              "See the fraud-prevention section below."),
            _("**Coupon and discount records.** The code you entered, the order it applied "
              "to and the discount amount."),
            _("**Subscription records**, if you choose an auto-renewing plan: the billing "
              "identifiers our payment processor gives us, the price per cycle, the renewal "
              "date and the renewal history."),
            _("**Support and assistant conversations**, including anything you type into "
              "the chat assistant."),
            _("**Optional profile data.** A display name, if you enter one, and a name you "
              "give an eSIM line to tell it from another."),
            _("**Acceptance records.** Which version of these documents you accepted, when, "
              "and from which address — so that both of us can tell later what you actually "
              "agreed to."),
        ),
    )),

    Clause("never-collect", _("What we never collect"), (
        UL(
            _("The content of your traffic — the sites you visit, your messages, your "
              "calls. We are a reseller of connectivity, and none of that reaches us."),
            _("Card numbers. Card payments are handled entirely by Stripe; we receive only "
              "a token and the outcome."),
            _("Identity documents. There is no KYC, no passport upload, no ID check."),
            _("Location beyond the country of the network your eSIM registers on, which is "
              "simply the destination you bought."),
            _("Advertising identifiers. We run no advertising SDK, we do not build "
              "profiles, and we do not sell or share personal data for advertising — "
              "including as \"sharing\" is defined by California law."),
        ),
    )),

    # --- app surfaces --------------------------------------------------------
    Clause("app-data", _("What the app collects"), (
        P(_("The app talks to the same service as the website and collects nothing extra "
            "for its own purposes. Specifically:")),
        UL(
            _("**Stored on your device only:** your sign-in token, so you stay signed in, "
              "and your theme and language choice. Signing out erases the token."),
            _("**Sent to us:** the same account, order and eSIM data described above, plus "
              "the app version and operating system version attached to error reports."),
            _("**Not collected:** your contacts, photos, calendar, microphone, precise "
              "location, advertising identifier, or any list of the apps installed on your "
              "device. The app requests no permission it does not need to show you a QR code."),
            _("**Push notifications**, if you allow them, use a token from Apple or Google "
              "that identifies the installation, not you. Refusing them costs you nothing "
              "but delivery and renewal alerts, which also arrive by email."),
        ),
        P(_("Purchases are made on our website, so no payment data passes through the app "
            "at all.")),
    ), surfaces=APP_SURFACES),

    Clause("fraud", _("Fraud prevention and chargeback defence"), (
        P(_("Digital goods delivered in seconds are a standard target for stolen cards, and "
            "a guest order has no account behind it. So, when an order is placed, we record "
            "the IP address the request came from, the browser user agent string, the "
            "browser language and the referring page, and we store them against that order.")),
        P(_("We use that record for three things and nothing else: to score an order for "
            "payment fraud before we provision a line, to answer a bank or card scheme when "
            "a payment is disputed, and to trace abuse of coupons or of the network itself. "
            "It is never used for advertising, profiling or tracking you across other sites, "
            "and we do not sell or share it for those purposes.")),
        P(_("The lawful basis is our legitimate interest in preventing fraud and in "
            "defending payment disputes, and, where card-scheme rules require it, our legal "
            "obligation. We keep this request data for 24 months from the order date and "
            "then delete it, which leaves a margin over the dispute windows the card schemes "
            "allow. The order itself, minus that request data, is kept for as long as "
            "accounting law requires.")),
        Callout(_("Deletion is automatic. A scheduled job clears the IP address, user agent, "
                  "language and referrer from every order older than 24 months, so this is a "
                  "promise the system keeps rather than one a person has to remember.")),
    )),

    Clause("coupons-data", _("Coupons and promotions"), (
        P(_("If you use a discount code we store the code, the order it was applied to and "
            "the amount it took off. Where a code is limited to one use per customer, we "
            "also keep a redemption record linked to your email address or account so the "
            "limit can be enforced.")),
        P(_("This is part of processing your order, and the record stays with the order for "
            "the same period. Discount codes are not used to build a marketing profile, and "
            "entering one does not sign you up to anything.")),
    )),

    Clause("subscriptions-data", _("Auto-renewing subscriptions"), (
        P(_("A subscription needs an account, because a recurring charge needs somewhere you "
            "can see and stop it. For each subscription we store the customer and "
            "subscription identifiers our payment processor returns, the price per cycle, "
            "the renewal interval, the date of the next renewal, how many times it has "
            "renewed and whether it is set to cancel at the end of the period. The card "
            "itself stays with the payment processor.")),
        P(_("We process this to perform the contract you entered into. You can cancel at any "
            "time from your dashboard or from the billing portal; cancelling stops future "
            "renewals and does not refund the period already delivered. The full commercial "
            "terms are in the [[doc:terms|terms of service]] and the [[doc:refund|refund "
            "policy]]. After a subscription ends, the billing record is kept for accounting.")),
    )),

    Clause("assistant-data", _("The chat assistant"), (
        P(_("The assistant in your account is an AI model answering support questions with "
            "the context of your own orders and eSIM lines. Conversations are stored against "
            "your account so the thread makes sense next time you open it, and so a human "
            "can pick it up where the model left off.")),
        P(_("Our support team can read those conversations. We review them to resolve "
            "escalations, to check answer quality and to catch abuse. Messages are sent to "
            "our AI provider, Anthropic, to generate a reply; under their commercial terms "
            "they are not used to train their models.")),
        P(_("Please do not paste passwords, full card numbers, recovery codes or identity "
            "documents into the chat. We never ask for any of them, and the assistant does "
            "not need them to help you. If you post something sensitive by accident, email "
            "us and we will delete that conversation.")),
        P(_("No decision that affects you is taken by the model alone. It cannot issue a "
            "refund, close an account or change an order; a person does that.")),
    )),

    Clause("why", _("Why we process it, and on what basis"), (
        Table(
            (_("What"), _("Why"), _("Lawful basis")),
            [
                (_("Email, order, eSIM data"), _("Sell and deliver the plan you asked for"),
                 _("Performance of a contract")),
                (_("Subscription billing data"), _("Run the recurring plan you started"),
                 _("Performance of a contract")),
                (_("IP, user agent, language, referrer"), _("Prevent fraud, defend disputes"),
                 _("Legitimate interest, and legal obligation under card-scheme rules")),
                (_("Order and payment records"), _("Accounting and tax"), _("Legal obligation")),
                (_("Support and assistant conversations"), _("Answer you, and improve support quality"),
                 _("Performance of a contract and legitimate interest")),
                (_("Product emails"), _("Tell you about things you did not ask about"), _("Consent")),
            ],
        ),
        P(_("Transactional email about your own orders is sent regardless of marketing "
            "preferences, because you need it to use what you bought.")),
    )),

    Clause("sharing", _("Who we share it with"), (
        P(_("Only the providers that make the service work, each for one purpose, each under "
            "a contract. The current list, with what each one receives and where it is, is "
            "on the [[doc:subprocessors|sub-processors page]] — kept separate so it can be "
            "updated when a provider changes without reissuing this policy.")),
        P(_("Beyond that list: a bank, card scheme or payment processor investigating a "
            "disputed payment, limited to the evidence that dispute requires, and a public "
            "authority where the law actually compels it. We do not sell personal data, and "
            "we do not share it with advertisers.")),
    )),

    Clause("transfers", _("Where your data goes"), (
        P(_("We are established in Estonia and your data is held in the European Union — "
            "the database and the application both run in Frankfurt. Nothing has to leave "
            "the European Economic Area for you to buy and use an eSIM.")),
        P(_("Three providers do process data in the United States: the email service that "
            "delivers your QR code, the AI provider behind the chat assistant, and parts "
            "of Stripe's payment network. Those transfers rely on the EU–US Data Privacy "
            "Framework where the provider is certified under it, and otherwise on the "
            "European Commission's standard contractual clauses in our contract with them.")),
        P(_("The [[doc:subprocessors|sub-processors page]] names the region each provider "
            "processes in, so you can see exactly which of your data crosses and which "
            "does not.")),
    )),

    Clause("cookies-ref", _("Cookies and analytics"), (
        P(_("We set a session cookie so the site can keep you signed in and remember a guest "
            "order, a CSRF cookie that protects forms, and a cookie recording your chosen "
            "language. Your light or dark mode preference is not a cookie at all: it is "
            "stored in your own browser and never sent to us.")),
        P(_("The full list, including what analytics does and does not do, is in the "
            "[[doc:cookies|cookie policy]].")),
    )),

    Clause("retention", _("How long we keep it"), (
        Table(
            (_("Record"), _("Kept for")),
            [
                (_("Order, payment, coupon and subscription billing records"),
                 _("As long as accounting and tax law requires")),
                (_("IP address, user agent, browser language and referrer on an order"),
                 _("24 months from the order date, then deleted automatically")),
                (_("eSIM technical records"), _("While the line is live, and a short period after for support")),
                (_("Support tickets and assistant conversations"),
                 _("While your account is open, or sooner on request")),
                (_("Acceptance records for these documents"),
                 _("As long as the contract they relate to can be disputed")),
                (_("Closed account"), _("Deactivated and the email unlinked immediately; "
                                        "accounting records remain and are used for nothing else")),
            ],
        ),
    )),

    Clause("security", _("How we protect it"), (
        P(_("Traffic is encrypted in transit and the database is encrypted at rest. "
            "Passwords are stored only as salted hashes, so nobody here can read yours. "
            "Access to production data is limited to the people who run the service, and "
            "payment card details never reach our systems at all.")),
        P(_("If a breach ever affects your personal data and is likely to be a risk to you, "
            "we will tell you and the relevant supervisory authority within the time the law "
            "sets — 72 hours of becoming aware, under the GDPR.")),
    )),

    Clause("rights", _("Your rights"), (
        P(_("You can ask for a copy of your data, correction, deletion, or a portable "
            "export, and you can object to processing based on legitimate interest, "
            "including the fraud record described above — though we may need to keep it "
            "where a payment dispute is open. You can withdraw marketing consent at any "
            "time from the unsubscribe link or your account page.")),
        P(_("Email [[mail]] and we will action it within one month, free of charge, as the "
            "GDPR requires. We answer requests from anywhere, not only from the "
            "jurisdictions whose law compels it.")),
        P(_("You can also complain to a supervisory authority. Ours is the Estonian Data "
            "Protection Inspectorate — Andmekaitse Inspektsioon, aki.ee — and you may "
            "equally go to the authority in the EU country you live or work in.")),
        P(_("If you are in California: the categories above are all we collect, we do not "
            "sell or share personal information, we do not use it for cross-context "
            "behavioural advertising, and exercising any of these rights will never get you "
            "worse service or a worse price.")),
    )),

    Clause("deletion", _("Deleting your account"), (
        P(_("You can delete your account yourself, at any time, from your account page — "
            "[[url:account_delete|{host}/dashboard/account/delete/]]. No email to "
            "support, no waiting.")),
        P(_("Deleting cancels any active subscription with our payment processor first, so "
            "nothing can be charged again. It then erases your profile, your support "
            "tickets and your assistant conversations, and removes the IP address, browser "
            "and referrer recorded against your past orders.")),
        P(_("The order and payment records themselves stay, no longer linked to an account. "
            "Tax law requires an invoice record and Article 17(3)(b) of the GDPR is the "
            "exception that permits keeping one; it is used for nothing else.")),
        Callout(_("eSIM profiles you have already installed keep working until their validity "
                  "ends. Deleting the account does not stop a line you are travelling on — "
                  "but it does mean you can no longer see its data balance here.")),
    )),

    Clause("children", _("Children"), (
        P(_("The service is not for children. You must be at least 16 to hold an account or "
            "buy a plan, we do not knowingly collect data from anyone younger, and if we "
            "learn that we have, we delete it. If you believe a child has given us personal "
            "data, write to [[mail]] and we will remove it.")),
    )),

    Clause("privacy-changes", _("Changes and contact"), (
        P(_("This policy has a version and an effective date, both at the top of the page, "
            "and every earlier version is listed on the [[url:legal_changes|change history "
            "page]]. A change that materially affects how we use your data is announced by "
            "email to account holders before it takes effect.")),
        P(_("Data protection contact: [[mail]].")),
    )),
]}
