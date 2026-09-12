# eSIMsterr

**Connect without borders.** A travel eSIM storefront: one Django project that
sells prepaid mobile data, provisions it through the Yesim partner API and
delivers the QR code instantly. Server-rendered pages for customers and search
engines, plus a JSON API for a future mobile app.

```
core/               settings, urls, middleware, sitemaps, rate limiting
apps/common         shared template tags: icons, flags, money, data sizes
apps/accounts       email-based user, Google sign-in, transactional email
apps/catalog        Country / Region / Plan mirrored from the provider + pricing
apps/orders         orders, eSIM records, checkout, fulfilment, dashboard
apps/payments       Stripe Checkout, NOWPayments crypto, webhooks, cron trigger
apps/subscriptions  auto-renewing unlimited plans on Stripe subscriptions
apps/coupons        discount codes, redemption ledger, public coupon page
apps/support        AI assistant chat (signed-in) + ticket system
apps/seo            programmatic-SEO pages (price hub, payment, comparisons)
apps/providers      Yesim partner API client
apps/blog           travel guides
apps/api            JSON API for the mobile app (JWT)
templates/          every page; static/css/app.css is the whole design system
docs/seo/           keyword map and the raw keyword list, grouped by intent
assets-src/         the original logo and film files the derivatives come from
```

## Run it locally

```bash
python3 -m venv venv
./venv/bin/pip install -r requirements.txt
cp .env.example .env          # fill in YESIM_API_TOKEN at minimum
./venv/bin/python manage.py migrate
./venv/bin/python manage.py sync_plans        # mirrors the catalogue (~90s)
./venv/bin/python manage.py seed_country_seo  # unique copy for 148 destinations
./venv/bin/python manage.py seed_content      # launch blog posts
./venv/bin/python manage.py createsuperuser
./venv/bin/python manage.py runserver
```

Without payment keys the site runs end to end; checkout simply reports that
payments are not configured. Without `YESIM_API_TOKEN` the catalogue stays empty.

## How a sale works

1. **Checkout** creates an `Order` in `pending`, applies a coupon if one was
   entered, records the request fingerprint, and hands off to Stripe Checkout or
   a NOWPayments invoice.
2. The provider calls back to `/webhooks/stripe/` or
   `/webhooks/nowpayments/ipn/`, both signature-verified.
3. `payments.services.settle_payment` is the single door money comes through. It
   marks the order paid and, on commit, calls fulfilment. An underpaid crypto
   invoice is recorded but **never** provisions.
4. `orders.services.fulfill_order` issues the eSIM (one provider call, plan
   attached) or tops up an existing one, then emails the QR code. It is
   idempotent and locked, so a webhook retry, the admin action and the cron
   sweeper cannot double-provision.
5. If the provider fails, the order stays `paid` with the error recorded, the
   operator is emailed, and `manage.py retry_orders` picks it back up. **The sale
   is never lost.**

A subscription cycle takes the same path: each paid Stripe invoice creates a real
`Order` and runs it through `fulfill_order`, so revenue, margin and fulfilment
have exactly one implementation.

## Pricing and the discount you advertise

Wholesale arrives in EUR. `apps/catalog/pricing.py` converts to USD, applies a
markup with a minimum margin and a price floor, then rounds up to a `.49`/`.99`
ending.

| Variable | Default | Meaning |
|---|---|---|
| `EUR_USD_RATE` | `1.10` | Wholesale EUR to retail USD |
| `PRICING_MARKUP` | `1.65` | Multiplier on cost, our selling price |
| `PRICING_MIN_MARGIN_USD` | `0.60` | Floor on absolute margin per sale |
| `PRICING_MIN_PRICE_USD` | `1.49` | Never sell below this |
| `PRICING_COMPARE_MULTIPLIER` | `4.0` | Cost multiplier for the struck-through list price |
| `SUBSCRIPTION_DISCOUNT_PCT` | `15` | Standing discount for subscribing |

The struck-through figure is **cost x 4**, which is roughly what the big eSIM
apps charge for the same wholesale supply, so the advertised percentage lands
between 50 and 60 percent on most plans. It is presented as the going market
rate, never as a former eSIMsterr price, because claiming a former price we never
charged is misleading and, in the EU, regulated. If you change the multiplier,
keep it defensible: spot-check two or three competitors first.

`manage.py sync_plans --reprice-only` recomputes every price and list price after
a change. A per-plan `price_override_usd` in the admin always wins.

## Management commands

| Command | What it does |
|---|---|
| `sync_plans` | Mirror the catalogue, price it, refresh aggregates and badges |
| `sync_plans --reprice-only` | Recompute prices from stored costs, no API call |
| `seed_country_seo` | Unique intro, title and description for every destination |
| `sync_usage` | Refresh data usage and status for live eSIMs |
| `retry_orders` | Provision orders stuck in `paid` |
| `expire_coupon_holds` | Release coupon seats held by abandoned checkouts |
| `purge_fingerprints` | Enforce the IP retention window the privacy policy states |
| `yesim_status` | Show partner balance and plan count |
| `yesim_status --register-webhook` | Point the provider's notifications at this site |
| `seed_content` | Create the launch blog articles |

The same jobs are reachable over HTTP for external schedulers:
`/webhooks/cron/<task>/?token=$CRON_SECRET` where task is `sync-usage`,
`retry-orders`, `sync-plans` or `purge-fingerprints`.

## Brand assets and flags

Logos, the hero film and the derived favicons live in `static/img/` and
`static/video/`; `static/img/README.md` explains which file goes where and how
they were produced. Country flags are the flag-icons SVG set, vendored into
`static/vendor/flags/`.

**Never use emoji.** Emoji flags render as the bare country code on Windows, and
pictographs differ on every platform. Use `{% flag country.iso2 %}` and
`{% icon "name" %}` from `apps/common/templatetags/ui.py`.

## Languages

Every user-facing string is wrapped for translation, but only the locales listed
in `ENABLED_LANGUAGES` are served. Publishing `/tr/` pages full of English is
duplicate content, not localisation, so translate a locale first, then add its
code and redeploy. URLs use `i18n_patterns` with `prefix_default_language=False`,
so English stays on bare paths and adding a locale never moves an indexed URL.

```bash
./venv/bin/python manage.py makemessages -l tr -i venv
# translate locale/tr/LC_MESSAGES/django.po, then
./venv/bin/python manage.py compilemessages
# and set ENABLED_LANGUAGES=en,tr
```

## SEO

`docs/seo/keyword-map.md` is the plan: every keyword family classified by intent,
the page type that serves it, title and description patterns, and explicit
anti-spam rules about what **not** to build. `docs/seo/raw-keywords.txt` is the
working list. Read the keyword map before adding pages.

## Store-policy note

All payment happens on the website. The mobile API deliberately has **no**
in-app purchase endpoint: `POST /api/v1/checkout-url/` returns a web URL for the
app to open in the system browser. Keep it that way, or App Store review will
treat the app as selling digital goods outside their billing system.

## Deployment

See [DEPLOY.md](DEPLOY.md). Render web service plus Supabase Postgres;
`render.yaml` describes the cron jobs.
