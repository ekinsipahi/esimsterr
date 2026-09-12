"""Copy and configuration for the programmatic-SEO pages.

No prices live in this file on purpose. Every page reads its "from" price out of
the catalogue at request time, so a price change in the database shows up on all
of these pages at once and none of them can drift into lying.

The competitor pages are deliberately free of competitor prices: see the note
above COMPETITORS.
"""
from django.utils.translation import gettext_lazy as _

# ---------------------------------------------------------------------------
# Payment-intent pages  (/buy-esim-with-<slug>/)
# ---------------------------------------------------------------------------
# Each entry carries its own body copy. They are four different pages for four
# different searches, not one paragraph with the coin name swapped, because a
# reader who searched for USDT has a different worry (which chain) than a reader
# who searched for Bitcoin (how many confirmations).
PAYMENT_METHODS = {
    "crypto": {
        "label": _("Crypto"),
        "icon": "bitcoin",
        "eyebrow": _("Pay your way"),
        "h1": _("Buy an eSIM with crypto"),
        "seo_title": _("Buy an eSIM with crypto — no account, no KYC, from just $%(price)s"),
        "seo_description": _(
            "Pay for a travel eSIM with Bitcoin, USDT, Ether and more. No account, no KYC, QR code "
            "delivered as soon as the payment confirms. Plans from $%(price)s."
        ),
        "lead": _(
            "We take cryptocurrency for mobile data, which most eSIM sellers still do not. Choose a "
            "plan, pick crypto at checkout, send the amount shown on screen, and the QR code is in "
            "your inbox as soon as the network confirms the payment."
        ),
        "sections": [
            (_("What you can pay with"), [
                _("Crypto checkout runs through our payment processor, which handles the major coins "
                  "and stablecoins: Bitcoin, Ether, Tether, USD Coin, Litecoin, TRON, BNB, Solana and "
                  "a long tail of others. The live list, the exact network and the exact amount all "
                  "appear on the payment screen before you move anything, so nothing rests on you "
                  "guessing which asset we support this week."),
                _("Plans are priced in US dollars. The crypto amount is worked out from the rate at "
                  "the moment the payment screen opens and is held for a short window, which is the "
                  "one good reason to send straight away rather than an hour later."),
            ]),
            (_("No account, no passport, no KYC"), [
                _("Buying a week of mobile data should not require an identity file. There is no "
                  "account to create, no document to upload and no verification queue. We ask for an "
                  "email address so the QR code has somewhere to land, and that is the whole of it."),
                _("If you would rather not give out your usual address, an alias or forwarding address "
                  "works perfectly well. The eSIM is tied to the profile on your handset, not to a "
                  "name on a form."),
            ]),
            (_("How delivery works after you send"), [
                _("The order page watches for the payment and updates itself. When the transaction "
                  "confirms, the QR code appears there and the same code goes out by email, so you "
                  "have it in two places before you close the laptop."),
                _("Install the profile at home on Wi-Fi. The plan does not start counting until the "
                  "eSIM first connects to a network at your destination, so an early install costs "
                  "you nothing."),
            ]),
            (_("If something goes wrong"), [
                _("Crypto payments are one-way, so we would rather sort out a problem than argue "
                  "about it. If you underpaid, overpaid, sent late or sent on an unexpected network, "
                  "write to support with the transaction hash and the order reference and we will fix "
                  "the order by hand."),
            ]),
        ],
        "points": [
            ("lock", _("No identity checks"), _(
                "No account, no passport upload, no selfie. An email address and a payment is the "
                "entire purchase flow.")),
            ("zap", _("Delivered in minutes"), _(
                "The QR code is released automatically the moment the transaction confirms, day or "
                "night, with nobody in the loop.")),
            ("tag", _("Same price as paying by card"), _(
                "We do not add a surcharge for paying in crypto. The only extra is the network fee "
                "your own wallet charges to broadcast the transaction.")),
        ],
        "accepted": [
            _("Bitcoin (BTC)"), _("Ether (ETH)"), _("Tether (USDT)"), _("USD Coin (USDC)"),
            _("Litecoin (LTC)"), _("TRON (TRX)"), _("BNB"), _("Solana (SOL)"), _("Dogecoin (DOGE)"),
        ],
        "faq": [
            (_("Do I need an account to pay with crypto?"),
             _("No. Checkout takes an email address and a payment. You can create an account later if "
               "you want your eSIMs and top-ups in one place, but nothing forces you to.")),
            (_("How long does confirmation take?"),
             _("Usually a few minutes. It depends on the coin and how busy its network is: a "
               "stablecoin transfer on a fast chain clears almost immediately, an on-chain Bitcoin "
               "payment waits for a block. The order page updates by itself, so you can leave it open.")),
            (_("What happens if the rate moves while I am paying?"),
             _("The quoted amount is locked for a short window at the payment screen. If it expires "
               "before you send, the processor will show you a fresh quote rather than quietly "
               "accepting the wrong amount.")),
            (_("Can I get a refund to my wallet?"),
             _("Yes. An unused eSIM that has not been installed is refundable within 24 hours of "
               "purchase, and we refund crypto payments to a wallet address you give us.")),
            (_("Is paying in crypto anonymous?"),
             _("It is private, not anonymous. We never ask for identity documents and we do not know "
               "who you are, but a blockchain transaction is public by design and your email address "
               "is attached to the order so we can support it.")),
        ],
    },
    "bitcoin": {
        "label": _("Bitcoin"),
        "icon": "bitcoin",
        "eyebrow": _("BTC accepted"),
        "h1": _("Buy an eSIM with Bitcoin"),
        "seo_title": _("Buy an eSIM with Bitcoin — travel data from just $%(price)s"),
        "seo_description": _(
            "Pay for a travel eSIM in BTC. No account, no KYC, QR code delivered as soon as the "
            "transaction confirms. Data plans in %(count)s destinations from $%(price)s."
        ),
        "lead": _(
            "Bitcoin buys mobile data here. Pick a destination, choose Bitcoin at checkout, send the "
            "amount to the address on screen, and the eSIM lands in your inbox as soon as the "
            "transaction confirms."
        ),
        "sections": [
            (_("Why pay for travel data in BTC"), [
                _("A card issued at home is a nuisance abroad. Banks flag foreign merchants, "
                  "three-digit security steps arrive by SMS to a number you cannot receive on, and "
                  "the whole thing fails at the exact moment you have no data to sort it out. A "
                  "Bitcoin payment has none of those failure modes: your wallet does not care which "
                  "country you are standing in."),
                _("It is also the honest option for anyone who simply prefers not to hand a card "
                  "number to another website. We never see one either way, but with BTC there is "
                  "nothing to see in the first place."),
            ]),
            (_("Confirmations, fees and how long it takes"), [
                _("An on-chain Bitcoin payment is not instant. We wait for network confirmation "
                  "before releasing the eSIM, which on a quiet day is a matter of minutes and on a "
                  "congested day is longer. Set a normal fee rather than the cheapest one your wallet "
                  "offers, or the transaction will sit in the queue while you sit at the gate."),
                _("The network fee goes to miners, not to us. We do not add anything on top of the "
                  "dollar price for paying this way."),
            ]),
            (_("The amount is quoted and held"), [
                _("Plans are priced in US dollars, so the payment screen converts to BTC at the rate "
                  "at that moment and holds the quote for a short window. Send the exact amount "
                  "displayed - not a rounded version of it - and the order matches itself "
                  "automatically."),
                _("If the window expires, refresh for a new quote instead of sending against the old "
                  "one."),
            ]),
            (_("What you do not need"), [
                _("No account. No passport. No proof of address. No app to install before you can "
                  "even see a price. You need an email address for the QR code and a phone that "
                  "supports eSIM."),
            ]),
        ],
        "points": [
            ("bitcoin", _("On-chain BTC"), _(
                "Send from any wallet or exchange to the address shown. Nothing custodial, nothing to "
                "sign up for.")),
            ("clock", _("Released on confirmation"), _(
                "The order page polls for you and hands over the QR code the moment the network "
                "confirms the transaction.")),
            ("shield", _("No card, no bank in the way"), _(
                "No foreign-transaction block, no 3-D Secure code sent to a phone number you cannot "
                "reach while abroad.")),
        ],
        "accepted": [
            _("Bitcoin (BTC), on-chain"),
            _("Any wallet or exchange withdrawal"),
            _("Exact quoted amount, held for a short window"),
        ],
        "faq": [
            (_("How many confirmations do you wait for?"),
             _("We follow the payment processor's confirmation policy for BTC, which is designed to "
               "release fast without accepting an unconfirmed transaction. In practice most orders "
               "complete within minutes of the transaction being broadcast with a sensible fee.")),
            (_("What if I send slightly the wrong amount?"),
             _("Underpayments and overpayments are recoverable. Contact support with the transaction "
               "hash and the order reference and we will either release the eSIM or return the "
               "difference.")),
            (_("Can I pay from an exchange account?"),
             _("Yes, but check the withdrawal fee your exchange deducts, because it can leave the "
               "received amount short of the quote. Sending from a self-custody wallet avoids that.")),
            (_("Do you accept Bitcoin for top-ups too?"),
             _("Yes. Top-ups use the same checkout, so you can add data to an eSIM you already "
               "installed and pay for it in BTC.")),
        ],
    },
    "usdt": {
        "label": _("USDT"),
        "icon": "credit-card",
        "eyebrow": _("Stablecoin accepted"),
        "h1": _("Buy an eSIM with USDT"),
        "seo_title": _("Buy an eSIM with USDT (Tether) — data plans from just $%(price)s"),
        "seo_description": _(
            "Pay for a travel eSIM in USDT. Dollar-priced plans, no account, no KYC, instant QR "
            "delivery. The checkout shows the exact network and address. From $%(price)s."
        ),
        "lead": _(
            "USDT is the least dramatic way to pay for data. Plans are priced in dollars and Tether "
            "is pegged to the dollar, so the number you are quoted is the number you send and nothing "
            "moves underneath you while the transfer settles."
        ),
        "sections": [
            (_("Why a stablecoin is the practical choice"), [
                _("With a volatile coin there is always a gap between the quote and the confirmation, "
                  "and one of the two parties carries that risk. With USDT there is essentially no "
                  "gap. You see a dollar price, you send a dollar-equivalent amount, the order "
                  "matches, the eSIM is released."),
                _("It also makes refunds tidy. If you cancel an unused eSIM within the refund window, "
                  "the amount that comes back is the amount that went out rather than an argument "
                  "about exchange rates."),
            ]),
            (_("Send on the network the checkout names"), [
                _("USDT exists on several blockchains, and a transfer sent on the wrong one is slow "
                  "and painful to recover. The payment screen shows the network next to the address. "
                  "Copy both. If your wallet asks which chain to use, use that one and no other."),
                _("Transfer fees differ enormously between chains, so if your wallet supports more "
                  "than one of the networks on offer, the cheaper option is usually worth taking."),
            ]),
            (_("Delivery is automatic"), [
                _("Stablecoin transfers confirm quickly, so the usual experience is that the order "
                  "page updates while you are still looking at it. The QR code appears there and is "
                  "emailed to you at the same time."),
                _("Install the profile on Wi-Fi before you travel. The plan starts on first "
                  "connection at your destination, not on install."),
            ]),
            (_("No account and no verification"), [
                _("There is no sign-up wall in front of the price, no identity check and no minimum "
                  "order. An email address is the only thing we need, and it exists so the QR code "
                  "has somewhere to go."),
            ]),
        ],
        "points": [
            ("percent", _("No exchange-rate drift"), _(
                "A dollar-pegged token against a dollar price means the quote and the settlement "
                "agree with each other.")),
            ("zap", _("Confirms quickly"), _(
                "Most USDT transfers settle in well under a minute, so the eSIM is usually released "
                "before you have switched tabs.")),
            ("info", _("The network is shown, not guessed"), _(
                "Address and chain appear together at checkout, which is the single most common way "
                "a stablecoin payment goes wrong elsewhere.")),
        ],
        "accepted": [
            _("Tether (USDT) on the networks shown at checkout"),
            _("USD Coin (USDC) as an alternative stablecoin"),
            _("Exact amount and network displayed before you send"),
        ],
        "faq": [
            (_("Which USDT network should I use?"),
             _("Whichever one the payment screen displays for your order. It names the chain next to "
               "the deposit address, and sending on a different chain is the one mistake that needs "
               "manual recovery.")),
            (_("Is the price the same as paying by card?"),
             _("Yes. The dollar amount does not change with the payment method. You pay the network "
               "transfer fee your wallet charges, and nothing to us.")),
            (_("How fast is the eSIM delivered?"),
             _("As soon as the transfer confirms, which for USDT is normally a matter of seconds to a "
               "couple of minutes. The QR code appears on the order page and in your email.")),
            (_("Can I pay with USDC instead?"),
             _("Yes. USDC and the other major stablecoins appear in the same checkout, and everything "
               "on this page applies to them in the same way.")),
        ],
    },
    "card": {
        "label": _("Card"),
        "icon": "credit-card",
        "eyebrow": _("Cards and wallets"),
        "h1": _("Buy an eSIM with a card"),
        "seo_title": _("Buy an eSIM with a card — Visa, Mastercard, Amex, from just $%(price)s"),
        "seo_description": _(
            "Pay for a travel eSIM by card: Visa, Mastercard and Amex through Stripe, plus Apple Pay "
            "and Google Pay. No account, no subscription. From $%(price)s."
        ),
        "lead": _(
            "Cards work the way you would expect and nothing clever happens. Stripe runs the "
            "checkout, we never see the card number, and the QR code is on screen before you have put "
            "your wallet away."
        ),
        "sections": [
            (_("What we accept"), [
                _("Visa, Mastercard and American Express, along with the wallets your device offers - "
                  "Apple Pay and Google Pay appear automatically when your browser and phone support "
                  "them, which saves typing a card number on a hotel Wi-Fi connection."),
                _("Everything is charged in US dollars. If your account is held in another currency, "
                  "your bank converts at its own rate, and a card with no foreign-transaction fee is "
                  "worth using here as everywhere else."),
            ]),
            (_("Your card details never reach our servers"), [
                _("Payment pages are hosted by Stripe. The card number goes from your browser to "
                  "them, and what comes back to us is a yes or a no plus the last four digits for "
                  "your receipt. There is no card data on our side to leak."),
                _("Your bank may add a 3-D Secure step, which is the one-tap approval in your banking "
                  "app. It is normal and it is not us asking for anything extra."),
            ]),
            (_("One payment, not a subscription"), [
                _("A plan is a single purchase. Nothing renews by itself, there is no membership fee "
                  "and there is no stored card quietly charging you next month. When you need more "
                  "data you buy a top-up on purpose, and it goes onto the eSIM you already have."),
                _("If you specifically want a plan that renews, that is a separate, clearly labelled "
                  "choice - never the default hidden under a price."),
            ]),
            (_("If your card is declined"), [
                _("Foreign merchants get flagged, particularly on the first attempt from an unusual "
                  "location. Approve the transaction in your banking app and try again, or switch to "
                  "another card. Crypto checkout is there as a fallback when a bank will not "
                  "cooperate and your flight will not wait."),
            ]),
        ],
        "points": [
            ("credit-card", _("Visa, Mastercard, Amex"), _(
                "Plus Apple Pay and Google Pay where your device supports them, with no extra fee "
                "from us for any of them.")),
            ("lock", _("Hosted by Stripe"), _(
                "PCI handling stays with the payment processor. We store an order and an email "
                "address, never a card number.")),
            ("repeat", _("No auto-renew by default"), _(
                "One plan, one charge. Top-ups are deliberate purchases, not a standing order.")),
        ],
        "accepted": [
            _("Visa"), _("Mastercard"), _("American Express"), _("Apple Pay"), _("Google Pay"),
        ],
        "faq": [
            (_("Do I need an account to pay by card?"),
             _("No. Guest checkout takes an email address and a card. An account is optional and only "
               "exists to keep your eSIMs, orders and top-ups together.")),
            (_("Which currency am I charged in?"),
             _("US dollars. Your bank converts to your home currency at its own rate if your account "
               "is held in something else.")),
            (_("Will anything renew automatically?"),
             _("Not unless you deliberately choose a renewing plan. A standard data plan is a one-off "
               "purchase and expires on its own.")),
            (_("Is my card stored?"),
             _("Not by us. Stripe handles the payment and we keep only the order record and the last "
               "four digits shown on your receipt.")),
            (_("My bank keeps declining the payment. What now?"),
             _("Approve it in your banking app if it asks, then retry. If the bank will not budge, "
               "crypto checkout takes about a minute and needs no bank at all.")),
        ],
    },
}


# ---------------------------------------------------------------------------
# Comparison pages  (/alternatives/<slug>/)
# ---------------------------------------------------------------------------
# HONESTY CONSTRAINT - read before editing.
# We do not hold verified, current pricing for any of these companies. Their
# prices change, vary by destination and vary by promotion, so any number we
# printed here would be stale within weeks and would be a lie in the meantime.
# So: no competitor prices, anywhere, in any form - not in copy, not in a table,
# not as an "average", not as a "typical". The comparison rows below therefore
# state what WE verifiably do, and tell the reader exactly what to look for on
# the other site so they can check rather than trust us. Our own live price is
# rendered from the database next to that invitation.
# If you are tempted to "improve" this page by adding their numbers: don't.
COMPARE_ROWS = [
    (_("Price per GB and per day"),
     _("Printed on every plan, next to the price. You never have to divide anything yourself."),
     _("Look for a per-GB figure on the plan list. If it is missing, divide the price by the "
       "gigabytes before you compare.")),
    (_("Account needed to buy"),
     _("No. Checkout takes an email address and a payment, and an account is optional afterwards."),
     _("Try reaching their checkout without creating an account or installing an app first.")),
    (_("Crypto accepted"),
     _("Yes. Bitcoin, USDT, Ether and other major coins, with no surcharge."),
     _("Check the payment options at their checkout, not the marketing page.")),
    (_("Subscription or auto-renew"),
     _("Never by default. A plan is a one-off purchase that expires on its own."),
     _("Read the small print under the price for renewal wording and stored-card terms.")),
    (_("Delivery"),
     _("QR code on the confirmation page and by email the moment payment clears, plus a one-tap "
       "install link on iPhone."),
     _("Check whether the profile is delivered inside an app only, and what happens if you lose the "
       "phone it was installed on.")),
    (_("Top-ups"),
     _("Added to the eSIM you already installed. No second QR code, no second profile."),
     _("Check whether more data means a brand new profile to install.")),
    (_("Refund before install"),
     _("Unused, uninstalled eSIMs are refunded within 24 hours of purchase."),
     _("Find the refund window and the exact wording that voids it.")),
    (_("Coverage on one plan"),
     _("Single-country plans plus regional plans covering whole continents, all listed publicly with "
       "their prices."),
     _("Compare like for like: same destination, same gigabytes, same number of days.")),
]

COMPETITORS = {
    "airalo": {
        "name": "Airalo",
        "descriptor": _("one of the best known travel eSIM apps, and for many travellers the first "
                        "eSIM they ever installed"),
        "lead": _(
            "If you have heard of travel eSIMs at all, you have probably heard of Airalo. It is a "
            "large, app-first marketplace with a wide catalogue. We are a website that sells the same "
            "kind of thing without the app, without the account and without the advertising budget "
            "baked into the price."
        ),
        "angle": [
            _("The structural difference is distribution. An app-first business has to buy its "
              "installs, and app-install advertising is expensive, continuous and ultimately paid for "
              "by whoever buys the data. We do not run app-install campaigns, because there is no app "
              "to install: the site works in any browser and the eSIM lives in your phone settings "
              "where it belongs."),
            _("The second difference is what we show you. Every plan here publishes its price per "
              "gigabyte and per day next to the headline price, which makes a 3 GB plan and a 5 GB "
              "plan directly comparable instead of a puzzle. Compare that with whatever you are "
              "looking at and you will know within ten seconds which is better value."),
        ],
        "extra_rows": [
            (_("App required"),
             _("No app. Buy in a browser, install the profile into your phone's own settings, manage "
               "it from any device."),
             _("Check whether buying, topping up and support all assume the app.")),
        ],
        "reasons": [
            ("percent", _("Thin margin, not a marketing budget"), _(
                "We buy wholesale and add a small margin. Nothing in your price is funding an "
                "app-install campaign.")),
            ("bitcoin", _("Crypto at checkout"), _(
                "Bitcoin, USDT and other major coins, which almost nobody in this category accepts.")),
            ("list", _("Every price in public"), _(
                "The whole catalogue, including the per-GB maths, is on the open web with no download "
                "required to see it.")),
        ],
        "faq": [
            (_("Is this an Airalo reseller?"),
             _("No. We are an independent seller with our own supply, our own pricing and our own "
               "support. We are not affiliated with Airalo in any way.")),
            (_("Will the coverage be the same?"),
             _("Travel eSIMs from every seller ride on the same local networks - there are only so "
               "many mobile operators in any country. Each destination page lists the operators your "
               "eSIM will use, so you can check before you buy rather than after.")),
            (_("Do you have an app?"),
             _("No, and that is deliberate. Everything runs in the browser, and the eSIM itself is "
               "managed in your phone's normal mobile-data settings.")),
        ],
    },
    "holafly": {
        "name": "Holafly",
        "descriptor": _("a travel eSIM brand built around unlimited-data plans"),
        "lead": _(
            "Holafly made its name on unlimited data. We sell unlimited plans too, but we also sell "
            "sized ones, and we think the choice matters: most trips do not need unlimited, and "
            "paying for it anyway is the most common way travellers overspend on data."
        ),
        "angle": [
            _("Unlimited is the right answer when you are tethering a laptop for a fortnight or "
              "streaming every evening. It is the wrong answer for a long weekend of maps, messaging "
              "and a couple of video calls, where a small bundle costs a fraction of it. Because we "
              "publish the price per day and per gigabyte on every plan, the comparison is right "
              "there and you can pick the cheaper one honestly."),
            _("We are also plain about what unlimited means anywhere in this industry: no data cap and "
              "no overage bill, but local networks do apply fair-use shaping to extreme continuous "
              "use, mostly heavy tethering. Anyone telling you otherwise is selling you a network "
              "they do not operate."),
        ],
        "extra_rows": [
            (_("Sized plans as well as unlimited"),
             _("Both. Bundles from small to large plus unlimited durations, side by side, with the "
               "per-day price on each."),
             _("Check whether a smaller, cheaper plan is offered at all for your destination, or only "
               "unlimited.")),
        ],
        "reasons": [
            ("layers", _("Pick the size you actually need"), _(
                "Sized bundles and unlimited plans sit next to each other, priced per day, so the "
                "cheaper choice is visible.")),
            ("infinity", _("Unlimited where it earns its place"), _(
                "Unlimited durations in a large share of destinations, for the trips that genuinely "
                "warrant them.")),
            ("info", _("Straight talk about fair use"), _(
                "We describe shaping honestly rather than promising something no operator delivers.")),
        ],
        "faq": [
            (_("Do you sell unlimited data plans?"),
             _("Yes, in a large share of destinations, for durations from about a week to a month. "
               "They are listed alongside sized bundles so you can compare the daily price.")),
            (_("Is unlimited really unlimited?"),
             _("There is no cap and no overage bill from us. Local networks apply fair-use shaping to "
               "extreme continuous use, which in practice affects heavy tethering rather than normal "
               "travel use. That is true of every unlimited travel eSIM, whoever sells it.")),
            (_("How do I know which is cheaper for my trip?"),
             _("Look at the price per day on both. If your trip is short and light on data, a sized "
               "bundle usually wins; if you are working off the connection for weeks, unlimited "
               "usually does.")),
        ],
    },
    "saily": {
        "name": "Saily",
        "descriptor": _("a travel eSIM service from the team behind NordVPN"),
        "lead": _(
            "Saily comes out of a security company, and its pitch bundles travel data with security "
            "extras. Ours does not bundle anything: you are buying mobile data, at the thinnest "
            "margin we can run on, and whatever else you use is your business."
        ),
        "angle": [
            _("Bundles are fine when you want everything in the bundle. They are a way of paying for "
              "things you do not want when you do not. If you already run a VPN, or you have decided "
              "you do not need one, a data plan with nothing strapped to it is simply cheaper per "
              "gigabyte, and the per-gigabyte figure is printed on every plan here so you can check "
              "that claim rather than take it."),
            _("On privacy, the relevant fact about us is small and verifiable: we never see your "
              "traffic, and we hold an email address, your orders and the usage counter the network "
              "reports. There is no account required to buy in the first place, which is a stronger "
              "privacy position than any feature list."),
        ],
        "extra_rows": [
            (_("Bundled extras in the price"),
             _("None. You are paying for data and nothing else."),
             _("Work out what the bundled software is worth to you before comparing prices.")),
        ],
        "reasons": [
            ("tag", _("Data, unbundled"), _(
                "No security suite folded into the price of your gigabytes.")),
            ("lock", _("Nothing to sign up for"), _(
                "No account is required to buy, which is the simplest privacy guarantee there is.")),
            ("bitcoin", _("Crypto accepted"), _(
                "Pay in Bitcoin or USDT if you would rather not attach a card to the purchase.")),
        ],
        "faq": [
            (_("Do you include a VPN?"),
             _("No. We sell mobile data. If you want a VPN, choose one on its own merits rather than "
               "because it came attached to a SIM.")),
            (_("Is the connection secure without one?"),
             _("You are on a mobile network rather than a public hotspot, and modern apps and sites "
               "are encrypted end to end. A VPN changes who can see your traffic metadata, which may "
               "or may not matter to you.")),
            (_("What do you store about me?"),
             _("An email address, your orders, and the data-usage counter the network reports for "
               "your eSIM. We never see the content of your traffic.")),
        ],
    },
    "nomad": {
        "name": "Nomad",
        "descriptor": _("a travel eSIM seller with a wide regional catalogue"),
        "lead": _(
            "Nomad and eSIMsterr are aimed at roughly the same traveller: someone crossing borders "
            "who wants one profile to keep working. The differences worth knowing are structural - "
            "how you pay, whether you need an account, and whether the per-gigabyte price is put in "
            "front of you or left for you to calculate."
        ),
        "angle": [
            _("We sell regional plans covering whole continents alongside single-country plans, and "
              "both are listed publicly with the price per gigabyte and per day attached. For a "
              "multi-country trip the regional plan is nearly always cheaper than a handful of "
              "single-country ones, and because the numbers are on the page you can prove that to "
              "yourself in a minute."),
            _("Payment is the other structural difference. We take cards through Stripe and crypto "
              "through our processor, there is no credit balance to preload, and there is no account "
              "in the way of the checkout."),
        ],
        "extra_rows": [
            (_("Credits or wallet balance"),
             _("None. You pay for the plan you are buying, when you buy it."),
             _("Check whether you have to preload a balance, and what happens to unspent credit.")),
        ],
        "reasons": [
            ("globe", _("Regional plans that cross borders"), _(
                "One profile for a whole continent, reconnecting to the next local network on its "
                "own.")),
            ("percent", _("The maths is done for you"), _(
                "Price per gigabyte and per day on every plan, so comparisons take seconds.")),
            ("credit-card", _("Pay once, no balance to top up"), _(
                "No wallet to preload and no unspent credit to lose track of.")),
        ],
        "faq": [
            (_("Do you sell regional plans?"),
             _("Yes - continental and multi-country plans covering large groups of destinations on a "
               "single profile, plus a global plan for long routes.")),
            (_("Is a regional plan cheaper than several country plans?"),
             _("For two or more countries, almost always. The regions page shows what each plan "
               "covers and what it costs, so you can check against your own itinerary.")),
            (_("Do I need to preload credit?"),
             _("No. Each plan is bought and paid for on its own.")),
        ],
    },
    "ubigi": {
        "name": "Ubigi",
        "descriptor": _("a travel eSIM service operated by the connectivity provider Transatel"),
        "lead": _(
            "Ubigi comes from the operator side of the industry. We come from the opposite direction: "
            "a shop that buys wholesale data and resells it as thinly as it can, with every price and "
            "every plan visible on the open web."
        ),
        "angle": [
            _("Practically, the differences a traveller notices are about buying rather than "
              "networking. There is no account here, no app, and no verification step: an email "
              "address and a payment produces a QR code. Crypto is accepted alongside cards. Nothing "
              "renews unless you deliberately choose it."),
            _("On the technical side, what you get is a standard eSIM profile installed through a QR "
              "code or a one-tap link, sitting in your phone's own settings next to your normal SIM. "
              "Your existing number keeps handling calls and messages while the eSIM carries data."),
        ],
        "extra_rows": [
            (_("Where the profile lives"),
             _("A standard QR or one-tap LPA profile in your phone's own eSIM settings. No app "
               "involved in installing or using it."),
             _("Check whether installation, top-ups or support route through an app.")),
        ],
        "reasons": [
            ("qr", _("Standard QR install"), _(
                "Scan or tap once and the profile is in your phone's settings, where you can manage "
                "it forever.")),
            ("user", _("No account required"), _(
                "Buy as a guest. Create an account later only if you want your eSIMs in one place.")),
            ("bitcoin", _("Card or crypto"), _(
                "Stripe for cards, major coins for everyone else, at the same dollar price.")),
        ],
        "faq": [
            (_("Will my phone work with it?"),
             _("If it supports eSIM and is carrier-unlocked, yes. The compatible devices page lists "
               "the handsets and shows how to check yours in about ten seconds.")),
            (_("Can I keep my own number?"),
             _("Yes. Your physical SIM is untouched, so calls, SMS and WhatsApp stay on your own "
               "number while the eSIM carries data.")),
            (_("Do I need to install anything before I travel?"),
             _("Only the eSIM profile itself, on Wi-Fi, before you fly. No app, and the plan does not "
               "start counting until it connects at your destination.")),
        ],
    },
    "cellesim": {
        "name": "Cellesim",
        "descriptor": _("a smaller travel eSIM seller"),
        "lead": _(
            "With smaller sellers the questions are less about brand and more about substance: what "
            "is actually in the catalogue, what happens when something goes wrong, and whether the "
            "price is legible before you commit."
        ),
        "angle": [
            _("Our answer is to put everything in public. The full destination list, every plan, "
              "every price, the per-gigabyte and per-day maths, the operators your eSIM will use in "
              "each country and the refund terms are all on the open web, with no account and no app "
              "between you and them."),
            _("Support is a person on email rather than a maze, refunds on uninstalled eSIMs are "
              "handled within 24 hours of purchase, and top-ups go onto the profile you already have "
              "instead of making you reinstall anything."),
        ],
        "extra_rows": [
            (_("Catalogue visible without signing up"),
             _("Every destination, plan and price is listed publicly, and the operators behind each "
               "destination are named."),
             _("See how much of the catalogue you can inspect before being asked for an email "
               "address.")),
        ],
        "reasons": [
            ("list", _("Nothing hidden behind a login"), _(
                "The whole catalogue and all its prices are indexable, public pages.")),
            ("headset", _("Support you can reach"), _(
                "Email support with a real person, and a documented refund window.")),
            ("repeat", _("Top-ups, not reinstalls"), _(
                "More data goes onto the eSIM you already installed.")),
        ],
        "faq": [
            (_("How do I know the coverage is real?"),
             _("Each destination page names the local operators the eSIM connects to, so you can "
               "check them against the coverage you expect before buying.")),
            (_("What if the eSIM does not work when I land?"),
             _("Start with the troubleshooting page - data roaming switched off is the cause more "
               "often than anything else - and contact support if that does not solve it.")),
            (_("Can I get a refund?"),
             _("An unused, uninstalled eSIM is refundable within 24 hours of purchase. Once a profile "
               "is installed and has carried data it cannot be resold, so it is not refundable.")),
        ],
    },
}


# ---------------------------------------------------------------------------
# Use-case destination indexes  (/esim-for-<slug>/)
# ---------------------------------------------------------------------------
# rec_gb / rec_days / prefer_unlimited drive a live catalogue query: the page
# shows the cheapest real plan that fits the recommendation for each destination
# in iso2, so the shortlist and its prices are never written down here.
USE_CASES = {
    "travel": {
        "label": _("travel"),
        "eyebrow": _("For holidays and short trips"),
        "h1": _("eSIM for travel"),
        "seo_title": _("eSIM for travel — data plans for your trip from just $%(price)s"),
        "seo_description": _(
            "The travel eSIM done simply: pick your destination, install before you fly, land with "
            "data already working. No roaming charges, no airport SIM queue. From $%(price)s."
        ),
        "lead": _(
            "For a normal trip you need maps that load, messages that send and a boarding pass that "
            "opens on the way to the gate. That is a small amount of data and it should cost a small "
            "amount of money."
        ),
        "rec_gb": 3,
        "rec_days": 7,
        "prefer_unlimited": False,
        "rec_label": _("3-5 GB for a week away"),
        "sections": [
            (_("How much data a holiday actually uses"), [
                _("Maps, messaging, a few searches and the occasional photo upload run to roughly "
                  "half a gigabyte a day for most people. A week of that is comfortably inside 5 GB, "
                  "and 3 GB is enough if you are out walking rather than scrolling. Streaming video "
                  "on mobile data is what changes the arithmetic, and it changes it fast."),
                _("Buy for the trip you are taking rather than the trip you are worried about. If you "
                  "run out, a top-up goes onto the same eSIM in a couple of minutes, so there is no "
                  "reason to over-buy insurance data up front."),
            ]),
            (_("Install before you fly"), [
                _("Install the profile at home on Wi-Fi. The plan does not start counting until the "
                  "eSIM connects to a network at your destination, so an early install is free and "
                  "saves you fighting with airport Wi-Fi while jet-lagged."),
                _("Remember the one setting everyone misses: switch data roaming on for the eSIM "
                  "line. A travel eSIM technically roams on partner networks, so with that setting "
                  "off you will see signal bars and get no data."),
            ]),
        ],
        "tips": [
            ("map-pin", _("One country or many"), _(
                "A single-country plan is cheapest if you stay put. Crossing borders, a regional plan "
                "is almost always better value.")),
            ("smartphone", _("Keep your own number"), _(
                "Your physical SIM stays in the phone, so calls, SMS and WhatsApp carry on as usual "
                "while the eSIM carries data.")),
            ("hotspot", _("Share it"), _(
                "Personal hotspot works, so one plan can put a laptop or a travelling companion "
                "online too.")),
        ],
        "iso2": ["ES", "IT", "FR", "GR", "TR", "PT", "US", "JP", "TH", "AE", "MX", "GB"],
        "region_slugs": ["europe", "asia-pacific"],
        "faq": [
            (_("How much data do I need for a week abroad?"),
             _("Around 3-5 GB covers maps, messaging, browsing and a moderate number of photos. Add "
               "more if you plan to stream video or work off the connection.")),
            (_("When does the plan start?"),
             _("On first connection at your destination, not when you buy or install it.")),
            (_("Can I use it in more than one country?"),
             _("A country plan works in that country. For a multi-country trip, buy the regional plan "
               "that covers your route.")),
        ],
    },
    "business-trips": {
        "label": _("business trips"),
        "eyebrow": _("For working travel"),
        "h1": _("eSIM for business trips"),
        "seo_title": _("eSIM for business trips — reliable data from just $%(price)s"),
        "seo_description": _(
            "A business travel eSIM that works the moment you land: hotspot for the laptop, calls "
            "over Teams and Zoom, an itemised receipt for expenses. Plans from $%(price)s."
        ),
        "lead": _(
            "On a working trip the connection is not a convenience, it is the job. You need data that "
            "is live before you clear the airport, enough of it to tether a laptop, and a receipt "
            "your finance team will accept."
        ),
        "rec_gb": 5,
        "rec_days": 7,
        "prefer_unlimited": False,
        "rec_label": _("5-10 GB for a week of meetings"),
        "sections": [
            (_("Budget for the laptop, not just the phone"), [
                _("Video calls are the expensive part. An hour of Teams or Zoom at normal quality "
                  "runs to roughly a gigabyte, and a tethered laptop syncing mail and cloud drives "
                  "adds more in the background. For a week with a few calls a day, 10 GB is a safer "
                  "starting point than 5 GB."),
                _("If the trip is long or the calls are constant, an unlimited duration plan removes "
                  "the arithmetic entirely. The per-day price on each plan tells you at what point "
                  "that becomes the cheaper option."),
            ]),
            (_("Receipts and expenses"), [
                _("Every order produces an emailed confirmation with the amount, the destination and "
                  "the order reference, which is what an expenses system wants. Nothing renews "
                  "silently afterwards, so there is no surprise line on next month's card statement "
                  "to explain."),
            ]),
        ],
        "tips": [
            ("hotspot", _("Tether the laptop"), _(
                "Personal hotspot is supported, so the eSIM covers the machine you actually work on.")),
            ("headset", _("Calls over the apps you already use"), _(
                "Plans are data-only, which is fine: Teams, Zoom, Meet and WhatsApp all run over "
                "data.")),
            ("check-circle", _("Live before you leave the terminal"), _(
                "Install on Wi-Fi at home and it connects on landing, with no kiosk queue and no "
                "roaming bill to justify later.")),
        ],
        "iso2": ["US", "GB", "DE", "SG", "AE", "JP", "FR", "NL", "CH", "HK"],
        "region_slugs": ["europe", "asia-pacific", "north-america"],
        "faq": [
            (_("Can I tether my laptop?"),
             _("Yes. Personal hotspot works on our plans, and it is the main reason to buy a larger "
               "bundle than you think you need.")),
            (_("Will my work calls go through?"),
             _("Teams, Zoom, Meet, Slack and WhatsApp all run over data, so they work normally. The "
               "plan does not carry traditional voice calls or SMS.")),
            (_("Do I get an invoice for expenses?"),
             _("You get an emailed order confirmation showing the amount, destination and reference, "
               "which is what most expense systems need.")),
        ],
    },
    "digital-nomads": {
        "label": _("digital nomads"),
        "eyebrow": _("For working anywhere"),
        "h1": _("eSIM for digital nomads"),
        "seo_title": _("eSIM for digital nomads — monthly data from just $%(price)s"),
        "seo_description": _(
            "Month-long and unlimited eSIM plans for remote workers: tether the laptop, hop borders "
            "without changing SIM, top up from anywhere. Plans from $%(price)s."
        ),
        "lead": _(
            "Living out of a rucksack makes connectivity infrastructure. You want thirty-day plans "
            "rather than seven-day ones, enough data to work from a balcony when the cafe Wi-Fi is "
            "unusable, and no dependence on a shop in a city you are leaving on Thursday."
        ),
        "rec_gb": 20,
        "rec_days": 30,
        "prefer_unlimited": True,
        "rec_label": _("20 GB or unlimited, 30 days at a time"),
        "sections": [
            (_("Why unlimited usually wins for a month"), [
                _("A full-time remote worker on mobile data goes through a great deal more than a "
                  "tourist: calls, screen sharing, cloud sync and the occasional evening of "
                  "streaming. Once you are past roughly 20 GB in a month, the unlimited plan for the "
                  "same destination is often the cheaper line on the page, and every plan shows its "
                  "per-day price so you can check rather than guess."),
                _("Fair use is worth knowing about honestly: there is no cap and no overage bill, but "
                  "local networks shape extreme continuous use, which mostly means very heavy "
                  "tethering. An unlimited travel eSIM is an excellent primary connection and a poor "
                  "substitute for home broadband."),
            ]),
            (_("The border-hopping problem"), [
                _("If your month covers three countries, buying three country plans is both more "
                  "expensive and more admin. A regional plan keeps one profile alive across the whole "
                  "route and reconnects to each local network on its own."),
                _("Keep your home SIM in the phone for the bank codes and the two-factor messages "
                  "that follow you around, and let the eSIM carry the data."),
            ]),
        ],
        "tips": [
            ("infinity", _("Unlimited by duration"), _(
                "Pay for days rather than gigabytes when your usage is unpredictable.")),
            ("globe", _("Regional plans"), _(
                "One profile across a continent, which suits a route rather than a destination.")),
            ("repeat", _("Top up from anywhere"), _(
                "More data goes onto the eSIM you already installed, from any browser, in about a "
                "minute.")),
        ],
        "iso2": ["TH", "ID", "PT", "ES", "MX", "VN", "GE", "CO", "TR", "AE"],
        "region_slugs": ["southeast-asia", "europe", "latin-america", "global"],
        "faq": [
            (_("Are there 30-day plans?"),
             _("Yes, in most destinations, both as large bundles and as unlimited durations.")),
            (_("Can I keep one eSIM across several countries?"),
             _("With a regional or global plan, yes. A single-country plan only works in its own "
               "country.")),
            (_("Can I work off it full time?"),
             _("Plenty of people do. Budget generously for video calls and tethering, and read the "
               "fair-use note on unlimited plans before you replace a fixed line with one.")),
        ],
    },
    "students": {
        "label": _("students"),
        "eyebrow": _("For studying abroad"),
        "h1": _("eSIM for students abroad"),
        "seo_title": _("eSIM for students abroad — month-long data from just $%(price)s"),
        "seo_description": _(
            "Land in your university city with working data. No local contract, no credit check, no "
            "deposit — a month of data on your existing phone from $%(price)s."
        ),
        "lead": _(
            "Arriving for a semester is the worst possible time to have no connection: you need maps "
            "to the halls, a bank appointment booked, and your parents able to reach you before any "
            "of the local paperwork exists."
        ),
        "rec_gb": 10,
        "rec_days": 30,
        "prefer_unlimited": False,
        "rec_label": _("10-20 GB for the first month"),
        "sections": [
            (_("Cover the gap before the local contract"), [
                _("Local operators generally want an address, a bank account and sometimes a credit "
                  "check, none of which you have in week one. A month of eSIM data bridges that "
                  "exactly, and it costs a fraction of roaming on your home plan while you sort the "
                  "rest out."),
                _("Keep your home SIM in the phone. Bank one-time codes and family calls keep "
                  "arriving on the number everyone already has for you, which matters more in the "
                  "first fortnight than it does later."),
            ]),
            (_("What a student month looks like"), [
                _("Campus and accommodation Wi-Fi will carry most of the heavy lifting, so the eSIM "
                  "is mainly covering travel, city time and the days the university network is "
                  "having a bad afternoon. Ten to twenty gigabytes is usually generous for that."),
                _("If you are travelling at weekends, check whether a regional plan covering your "
                  "neighbouring countries costs less than a second country plan later."),
            ]),
        ],
        "tips": [
            ("user", _("No contract, no credit check"), _(
                "Nothing to sign, no deposit and no local address needed.")),
            ("calendar", _("Month-long plans"), _(
                "Thirty-day bundles that cover the settling-in period without committing you to "
                "anything.")),
            ("wifi", _("Wi-Fi does the rest"), _(
                "Campus and accommodation networks cover most of your usage, so the plan is smaller "
                "than you would guess.")),
        ],
        "iso2": ["GB", "DE", "FR", "ES", "IT", "NL", "PL", "US", "CA", "AU"],
        "region_slugs": ["europe"],
        "faq": [
            (_("Do I need a local bank account?"),
             _("No. You buy with a card or crypto and the eSIM arrives by email. Local contracts are "
               "what need a bank account, which is exactly the problem this solves.")),
            (_("Can my family still call me?"),
             _("Yes. Your own SIM stays in the phone with your usual number, and the eSIM only "
               "carries data.")),
            (_("What if I stay longer than a month?"),
             _("Top up the same eSIM for another month, or switch to a local contract once you have "
               "the paperwork. Nothing here renews automatically.")),
        ],
    },
    "long-stays": {
        "label": _("long stays"),
        "eyebrow": _("For a month or more"),
        "h1": _("eSIM for long stays"),
        "seo_title": _("eSIM for long stays — 30-day and unlimited plans from just $%(price)s"),
        "seo_description": _(
            "Staying a month or more? Thirty-day and unlimited eSIM plans, topped up on the same "
            "profile, with the price per day printed on every option. From $%(price)s."
        ),
        "lead": _(
            "Beyond about three weeks the economics change. Daily price matters more than headline "
            "price, top-ups matter more than the initial purchase, and the ability to extend without "
            "reinstalling anything matters most of all."
        ),
        "rec_gb": 20,
        "rec_days": 30,
        "prefer_unlimited": True,
        "rec_label": _("30-day plans, unlimited if you tether"),
        "sections": [
            (_("Read the per-day price, not the sticker"), [
                _("A 30-day plan that looks expensive next to a 7-day one is usually cheaper per day, "
                  "and the per-day figure is printed on every plan for exactly this reason. Work out "
                  "roughly how many days you are staying and compare that column."),
                _("If you are tethering a laptop daily or streaming in the evenings, an unlimited "
                  "duration removes the need to predict anything at all."),
            ]),
            (_("Extending without starting again"), [
                _("Top-ups attach to the eSIM profile you already installed. You buy more days or "
                  "more data from any browser and the same profile keeps working, so there is no "
                  "second QR code and no reinstall on a phone you now depend on."),
                _("If the stay stretches into several months, a local contract may eventually beat "
                  "any travel plan. Until the paperwork is done, this keeps you online without a "
                  "commitment."),
            ]),
        ],
        "tips": [
            ("calendar", _("Thirty days at a time"), _(
                "The standard long-stay unit, priced per day so the comparison is easy.")),
            ("repeat", _("Top up the same profile"), _(
                "Extending never means installing a new eSIM.")),
            ("infinity", _("Unlimited when usage is heavy"), _(
                "Worth it once you are past roughly 20 GB a month or tethering regularly.")),
        ],
        "iso2": ["ES", "PT", "IT", "MX", "TH", "ID", "TR", "GR", "GE", "VN"],
        "region_slugs": ["europe", "southeast-asia", "latin-america"],
        "faq": [
            (_("What is the longest plan you sell?"),
             _("Most destinations offer 30-day plans, and some go longer. You can also top up to "
               "extend rather than buying a new eSIM.")),
            (_("Does topping up need a new QR code?"),
             _("No. Top-ups apply to the profile already installed on your phone.")),
            (_("Is unlimited worth it for a month?"),
             _("If you tether or stream daily, usually yes. Compare the per-day price of the "
               "unlimited plan against the sized bundle you would otherwise buy twice.")),
        ],
    },
    "backpacking": {
        "label": _("backpacking"),
        "eyebrow": _("For multi-country routes"),
        "h1": _("eSIM for backpacking"),
        "seo_title": _("eSIM for backpacking — one plan across borders from just $%(price)s"),
        "seo_description": _(
            "Backpacking across several countries? A regional eSIM keeps one profile working the "
            "whole route, with no new SIM at every border. Plans from $%(price)s."
        ),
        "lead": _(
            "A backpacking route is a border problem, not a country problem. Buying a local SIM in "
            "each place means a queue, a language barrier and a new number every few days, at exactly "
            "the moments you most need a map."
        ),
        "rec_gb": 10,
        "rec_days": 30,
        "prefer_unlimited": False,
        "rec_label": _("A regional plan, 10 GB or more"),
        "sections": [
            (_("One profile for the whole route"), [
                _("Regional plans cover whole groups of countries on a single eSIM. You cross a "
                  "border, the profile reconnects to the next local network on its own, and nothing "
                  "on your phone needs touching. For any route with two or more countries this is "
                  "nearly always cheaper than a stack of single-country plans."),
                _("Check the coverage list on the regional page against your itinerary before you "
                  "buy. If one country on your route is missing, a small country plan for that leg "
                  "costs very little on top."),
            ]),
            (_("Practical things that go wrong on the road"), [
                _("Install the profile while you still have reliable Wi-Fi, not in a hostel car park "
                  "at midnight. Keep the QR code email, and keep your home SIM in the phone so bank "
                  "codes still reach you."),
                _("Data roaming must be switched on for the eSIM line. It is the single most common "
                  "reason a working eSIM appears not to work after a border crossing."),
            ]),
        ],
        "tips": [
            ("compass", _("Regional coverage"), _(
                "One plan across a continent, listed with the countries it covers.")),
            ("plane", _("No SIM shop at every stop"), _(
                "Nothing to buy on arrival, nothing to swap, nothing to lose.")),
            ("shield", _("Keep your own number"), _(
                "Your home SIM stays in the phone for calls, codes and everyone who already knows "
                "how to reach you.")),
        ],
        "iso2": ["TH", "VN", "ID", "MY", "PH", "LA", "KH", "TR", "GE", "MX"],
        "region_slugs": ["southeast-asia", "asia-pacific", "latin-america", "balkans", "global"],
        "faq": [
            (_("Is one eSIM enough for several countries?"),
             _("With a regional or global plan, yes. Check the covered-countries list against your "
               "route before buying.")),
            (_("What happens when I cross a border?"),
             _("The eSIM reconnects to a local network in the new country by itself, provided that "
               "country is covered by your plan.")),
            (_("Is a regional plan cheaper than buying each country?"),
             _("For two or more countries it almost always is. The per-day price on each plan makes "
               "the comparison quick.")),
        ],
    },
}


# ---------------------------------------------------------------------------
# Education page  (/what-is-esim/)
# ---------------------------------------------------------------------------
# (aspect, eSIM, physical SIM)
SIM_COMPARISON = [
    (_("Getting one"),
     _("Downloaded over the internet in about two minutes, at any hour."),
     _("Bought in a shop or posted to you, in opening hours, in a country you are not in yet.")),
    (_("Where it lives"),
     _("A chip soldered into the phone during manufacture."),
     _("A plastic card in a tray you need a pin to open.")),
    (_("Number of profiles"),
     _("Several stored at once on most modern phones, with one or two active together."),
     _("One per physical slot.")),
    (_("Switching networks"),
     _("A toggle in settings; no hardware involved."),
     _("Swap the card, and try not to drop the small one.")),
    (_("Travelling"),
     _("Add a local data profile and keep your own number on the physical SIM at the same time."),
     _("Remove your home SIM to use a local one, and lose your number until you swap back.")),
    (_("Losing it"),
     _("Nothing to lose. The profile can usually be reinstalled by the seller if the phone is "
       "replaced."),
     _("Easy to lose, and a replacement means another trip to a shop.")),
    (_("Security if the phone is stolen"),
     _("Cannot be pulled out and put in another handset."),
     _("Can be removed in seconds and used elsewhere.")),
    (_("Compatibility"),
     _("Needs a reasonably recent, carrier-unlocked phone."),
     _("Works in almost anything, including very old handsets.")),
]

EDUCATION_FAQ = [
    (_("What is an eSIM in simple terms?"),
     _("It is a SIM card built into your phone that can be programmed over the internet. Instead of "
       "collecting a piece of plastic, you scan a QR code and the mobile plan downloads onto the "
       "chip that is already inside the device.")),
    (_("Is an eSIM the same as dual SIM?"),
     _("They are related but not the same. Dual SIM means a phone can run two lines at once; an eSIM "
       "is one way of providing one of those lines. Most modern phones are dual SIM precisely "
       "because they pair a physical slot with an eSIM, which is why you can keep your own number "
       "and add travel data at the same time.")),
    (_("Can I use an eSIM and a physical SIM together?"),
     _("Yes, on any phone that supports both. Your physical SIM keeps handling calls, SMS and your "
       "existing number while the eSIM carries data, and you choose in settings which line is used "
       "for what.")),
    (_("Does an eSIM replace my normal number?"),
     _("No. A travel data eSIM adds a line; it does not touch the one you already have. Your number, "
       "your WhatsApp account and your bank's SMS codes stay exactly where they are.")),
    (_("Which phones support eSIM?"),
     _("iPhone XS and newer, Google Pixel 3 and newer, Samsung Galaxy S20 and newer, and many recent "
       "Xiaomi, Motorola, Huawei and Oppo models. The handset also has to be carrier-unlocked.")),
    (_("Can I move an eSIM to a new phone?"),
     _("Usually not by yourself. Most profiles can only be installed once, and moving one means the "
       "seller issuing a replacement. Install it on the phone you will actually travel with.")),
    (_("Does an eSIM work without Wi-Fi?"),
     _("Installing one needs an internet connection, which is why you install at home before you "
       "fly. Once installed, it connects to the mobile network on its own with no Wi-Fi involved.")),
    (_("Do eSIMs use more battery?"),
     _("Not meaningfully. Running two active lines uses slightly more power than one, because the "
       "phone maintains two connections, but the difference is small compared with screen time.")),
]

# ---------------------------------------------------------------------------
# Troubleshooting page  (/esim-not-working/)
# ---------------------------------------------------------------------------
# Ordered deliberately by how often each one is the actual cause. Data roaming
# is first because it is the answer far more often than everything below it
# combined.
DIAGNOSTIC_STEPS = [
    {
        "icon": "refresh",
        "title": _("Turn data roaming on for the eSIM line"),
        "body": [
            _("This is the cause more often than every other item on this page put together. A "
              "travel eSIM is technically roaming on partner networks, so with roaming switched off "
              "the phone shows signal bars and carries no data at all."),
            _("On iPhone: Settings, Mobile Service, tap the travel plan, then Mobile Data Options and "
              "switch Data Roaming on. On Android: Settings, Network and internet, SIMs, select the "
              "travel eSIM, then turn Roaming on."),
        ],
    },
    {
        "icon": "sim",
        "title": _("Set the eSIM as the line for mobile data"),
        "body": [
            _("Adding a second line does not automatically make it the one your phone uses for data. "
              "If your home SIM is still the data line you are either getting nothing or, worse, "
              "roaming charges from your own operator."),
            _("On iPhone: Settings, Mobile Service, Mobile Data, and choose the travel plan. On "
              "Android: Settings, Network and internet, SIMs, Mobile data, and select the eSIM. "
              "Leave your own SIM as the line for calls and SMS."),
        ],
    },
    {
        "icon": "signal",
        "title": _("Check the plan has actually started"),
        "body": [
            _("The clock starts on first connection at your destination, not at purchase. If you are "
              "still at home, the eSIM will show as installed but will not carry data, and that is "
              "correct behaviour rather than a fault."),
            _("Your dashboard shows the status and the data remaining once the plan is live. If it "
              "says the plan has not started and you have landed, move to the next step."),
        ],
    },
    {
        "icon": "refresh",
        "title": _("Restart, or toggle flight mode"),
        "body": [
            _("A phone that has just landed sometimes holds on to a network registration that no "
              "longer exists. Flight mode on, wait ten seconds, flight mode off is the quickest "
              "version of the fix; a full restart is the thorough one."),
            _("Give it a minute afterwards. Registering on a foreign network is not instantaneous."),
        ],
    },
    {
        "icon": "search",
        "title": _("Select a network manually"),
        "body": [
            _("If automatic selection has latched onto an operator your plan does not use, choose one "
              "of the supported operators by hand. Each destination page lists which operators your "
              "eSIM works with."),
            _("On iPhone: Settings, Mobile Service, tap the eSIM, Network Selection, turn Automatic "
              "off and pick from the list. On Android the equivalent sits under SIMs, Automatically "
              "select network."),
        ],
    },
    {
        "icon": "wifi",
        "title": _("Check the APN"),
        "body": [
            _("Most plans configure themselves, but some Android handsets need the access point name "
              "entered by hand. The correct APN for your plan is shown on the eSIM page in your "
              "dashboard and in your delivery email."),
            _("On Android: Settings, Network and internet, SIMs, select the eSIM, Access Point Names, "
              "and add a new APN with exactly that name. iPhones almost never need this."),
        ],
    },
    {
        "icon": "lock",
        "title": _("Confirm the phone is carrier-unlocked"),
        "body": [
            _("A handset locked to your home operator will install an eSIM profile and then refuse to "
              "use it. If the phone came on a contract and you have never used another operator's "
              "SIM in it, this is worth ruling out."),
            _("Your home operator can tell you the lock status and, usually, remove it. There is "
              "nothing we can do from our side about a locked handset."),
        ],
    },
    {
        "icon": "qr",
        "title": _("If the QR code will not install at all"),
        "body": [
            _("Installation needs an internet connection, so do it on Wi-Fi rather than on the mobile "
              "data you are trying to replace. Scan the code from another screen rather than from "
              "the phone doing the installing."),
            _("If the code has already been used, it will not install a second time. That usually "
              "means the profile is on the phone already, under a different label than you expect - "
              "check the list of mobile plans in settings before requesting a replacement."),
        ],
    },
]

# (symptom, what it usually means, what to do)
SYMPTOMS = [
    (_("Signal bars but no data"),
     _("Data roaming is off, or the eSIM is not set as the mobile data line."),
     _("Steps 1 and 2 above, in that order.")),
    (_("No service at all on the eSIM line"),
     _("The phone has not registered on a partner network yet, or the handset is locked."),
     _("Toggle flight mode, then try selecting a network manually.")),
    (_("Data worked and then stopped"),
     _("The bundle is used up, or the plan has expired."),
     _("Check the remaining data in your dashboard and buy a top-up if it is empty.")),
    (_("Very slow speeds"),
     _("A congested cell, a weak indoor signal, or fair-use shaping on an unlimited plan after very "
       "heavy use."),
     _("Try outdoors or in another area before assuming a fault.")),
    (_("The QR code will not scan"),
     _("It is being scanned from the same phone, or the profile is already installed."),
     _("Open the code on another screen, or check the existing plans list in settings.")),
    (_("Calls and SMS do not work"),
     _("Nothing is wrong. Travel plans carry data only."),
     _("Use WhatsApp, FaceTime or Telegram, and keep your own SIM for traditional calls.")),
]

TROUBLESHOOTING_FAQ = [
    (_("My eSIM says no service. What is the first thing to check?"),
     _("Data roaming for the eSIM line. It has to be switched on, because a travel eSIM roams on "
       "partner networks by design. This one setting accounts for most reports we receive.")),
    (_("Why do I have bars but no internet?"),
     _("Either roaming is off for that line, or your phone is still using your home SIM for mobile "
       "data. Both are two taps to fix in settings.")),
    (_("My plan has not started counting. Is it broken?"),
     _("Probably not. The plan begins on first connection at your destination, so before you land it "
       "will sit installed and idle. That is how it is supposed to work.")),
    (_("The QR code will not install."),
     _("Install over Wi-Fi, scan the code from a different screen, and check whether the profile is "
       "already on the phone under an unfamiliar name. If none of that helps, contact support and "
       "we will reissue it.")),
    (_("How do I know if my phone is locked?"),
     _("Ask your home operator, or try another operator's SIM in the handset. A locked phone accepts "
       "the profile and then refuses to connect with it.")),
    (_("Nothing on this page worked."),
     _("Contact support with your order reference and a screenshot of the eSIM settings screen. We "
       "can see the profile status from our side and will either fix it or refund it.")),
]

# ---------------------------------------------------------------------------
# Price hub  (/cheap-esim/)
# ---------------------------------------------------------------------------
CHEAP_FAQ = [
    (_("Why are your eSIM plans cheaper?"),
     _("Two reasons, both boring. We buy wholesale data and add a thin margin rather than a large "
       "one, and we do not spend money on app-install advertising, which is the single biggest cost "
       "in this category. There is no trick involving worse networks: travel eSIMs all ride on the "
       "same local operators.")),
    (_("Is a cheap eSIM worse quality?"),
     _("The network is the network. Your eSIM connects to the same national operators any other "
       "seller would use, and each destination page names them. What differs between sellers is the "
       "margin, not the radio.")),
    (_("What is the cheapest way to buy data for a trip?"),
     _("Work in price per gigabyte and per day rather than headline price, buy for the trip you are "
       "actually taking, and top up if you run out. Regional plans beat several country plans on any "
       "multi-country route.")),
    (_("Are there hidden fees?"),
     _("No. The price on the plan is the price you pay. There is no activation fee, no delivery fee "
       "and nothing renews on its own.")),
    (_("Do you run sales?"),
     _("We would rather keep the everyday price low than run a permanent fake sale. The prices on "
       "this page are simply our prices, pulled live from the catalogue as you load it.")),
    (_("Can I top up instead of buying a new eSIM?"),
     _("Yes, and it is usually cheaper. Top-ups attach to the profile already installed on your "
       "phone, so nothing is reinstalled and nothing is wasted.")),
]

# ---------------------------------------------------------------------------
# Price index  (/esim-prices/)
# ---------------------------------------------------------------------------
PRICES_FAQ = [
    (_("What does the from price mean?"),
     _("It is the cheapest live plan for that destination, whatever its size or duration. Open the "
       "destination to see the full ladder of plans with the price per gigabyte and per day on each.")),
    (_("Why do prices differ so much between countries?"),
     _("Wholesale data costs different amounts in different markets, and we pass that through rather "
       "than averaging it into one global price. Competitive markets are cheap; small or remote ones "
       "are not.")),
    (_("Are these prices in US dollars?"),
     _("Yes, every price on the site is in USD. Your bank converts if your account is in another "
       "currency.")),
    (_("How often do prices change?"),
     _("They follow our wholesale costs, so they move occasionally rather than daily. This table is "
       "generated from the live catalogue each time you load it, so it is never out of date.")),
]
