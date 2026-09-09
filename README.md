# eSIMsterr

Travel eSIM storefront: a single Django project that sells prepaid mobile data
plans, provisions them through the Yesim partner API, and delivers the QR code
instantly. Server-rendered pages for customers and search engines, plus a JSON
API for a future mobile app.

```
core/            settings, urls, middleware, sitemaps, rate limiting
apps/accounts    email-based user, signup/login, Google sign-in, transactional email
apps/catalog     Country / Region / Plan mirrored from the provider + pricing strategy
apps/orders      orders, eSIM records, checkout, fulfilment, customer dashboard
apps/payments    Stripe Checkout, NOWPayments crypto, webhooks, cron trigger
apps/providers   Yesim partner API client
apps/api         JSON API for the mobile app (JWT)
apps/blog        travel guides / SEO articles
apps/support     help centre + tickets
templates/       every page; static/css/app.css is the whole design system
```

## Run it locally

```bash
python3 -m venv venv
./venv/bin/pip install -r requirements.txt
cp .env.example .env          # then fill in YESIM_API_TOKEN at minimum
./venv/bin/python manage.py migrate
./venv/bin/python manage.py sync_plans        # mirrors the catalogue (~90s)
./venv/bin/python manage.py seed_content      # three launch blog posts
./venv/bin/python manage.py createsuperuser
./venv/bin/python manage.py runserver
```

Without payment keys the site still runs end to end; checkout simply reports that
payments are not configured. Without `YESIM_API_TOKEN` the catalogue stays empty.

## How a sale works

1. **Checkout** (`apps/orders/views.checkout`) creates an `Order` in `pending`
   and hands off to Stripe Checkout or a NOWPayments invoice.
2. The provider calls back — `POST /webhooks/stripe/` or
   `POST /webhooks/nowpayments/ipn/`, both signature-verified.
3. `payments.services.settle_payment` is the single door money comes through. It
   marks the order `paid` and, on commit, calls fulfilment. An underpaid crypto
   invoice is recorded but **never** provisions.
4. `orders.services.fulfill_order` issues the eSIM (`GET /new_esim` with the plan
   attached, one call) or tops up an existing one (`POST /add_plan_iccid`), then
   emails the QR code. It is idempotent and locked, so a webhook retry, the admin
   action and the cron sweeper cannot double-provision.
5. If the provider fails, the order stays `paid` with the error recorded, the
   operator is emailed, and `manage.py retry_orders` picks it back up. **The sale
   is never lost.**

## Pricing strategy

Wholesale arrives in EUR. `apps/catalog/pricing.py` converts to USD, applies a
markup with a minimum margin and a price floor, then rounds up to a `.49`/`.99`
ending. Every knob is an environment variable:

| Variable | Default | Meaning |
|---|---|---|
| `EUR_USD_RATE` | `1.10` | Wholesale EUR → retail USD |
| `PRICING_MARKUP` | `1.65` | Multiplier on cost |
| `PRICING_MIN_MARGIN_USD` | `0.60` | Floor on absolute margin per sale |
| `PRICING_MIN_PRICE_USD` | `1.49` | Never sell below this |

`manage.py sync_plans --reprice-only` recomputes every price after a change. A
per-plan `price_override_usd` in the admin always wins over the formula, so you
can hand-price a hero destination without touching the rest.

The `compare_at_usd` strike-through is a conservative estimate of what the big
eSIM apps charge (1.9× our price for data plans, 1.6× for unlimited). Real spot
checks put us at roughly half of Cellesim on the same allowance.

## Management commands

| Command | What it does |
|---|---|
| `sync_plans` | Mirror the provider catalogue, price it, refresh aggregates and badges |
| `sync_plans --reprice-only` | Recompute retail prices from stored costs, no API call |
| `sync_usage` | Refresh data usage and status for live eSIMs |
| `retry_orders` | Provision orders stuck in `paid` |
| `yesim_status` | Show partner balance and plan count |
| `yesim_status --register-webhook` | Point the provider's notifications at this site |
| `seed_content` | Create the launch blog articles |

The same jobs are reachable over HTTP for external schedulers:
`/webhooks/cron/<task>/?token=$CRON_SECRET` where task is `sync-usage`,
`retry-orders` or `sync-plans`.

## Store-policy note

All payment happens on the website. The mobile API deliberately has **no**
in-app purchase endpoint: `POST /api/v1/checkout-url/` returns a web URL for the
app to open in the system browser. Keep it that way, or App Store review will
treat the app as selling digital goods outside their billing system.

## Deployment

See [DEPLOY.md](DEPLOY.md). Short version: Render web service + Supabase
Postgres, `render.yaml` describes both cron jobs.
