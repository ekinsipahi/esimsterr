# Testing without spending money

Written for whoever runs the pre-release checks, on a phone.

There are two ways to test, and they answer different questions.

| | Admin test tool | Staging |
|---|---|---|
| Where | Production | `esimsterr-staging.onrender.com` |
| Payment | Skipped — balance is granted | **Real Stripe, test keys** |
| Card | none | `4242 4242 4242 4242` |
| Data | The real catalogue and real customers | Wiped on every deploy |
| Costs | Provider balance, if you provision | Provider balance, if you provision |
| Answers | "does the flow work" | "does paying work" |

Use the admin tool for everything except the card. Use staging for the card,
because testing a payment against live keys means either real money or a
half-tested flow.

## The admin test tool

Set `ADMIN_TEST_TOKEN` to a long random value on the service you want to test.
**Empty disables it completely** — there is no default, because a payment bypass
that ships enabled is a bypass somebody else finds. Clear it when you are done.

Without the token every endpoint answers `404`, not `403`: it does not admit to
existing.

On the phone: Profile, then tap the version line at the bottom seven times.
Paste the token.

It grants balance and settles orders. It does **not** bypass buying — coupons,
provisioning, device binding and the order builder all run exactly as they do
for a customer. A test that avoids the real path proves nothing about it.

```bash
# Is it on?
curl -H "X-Admin-Test-Token: $TOKEN" https://esimsterr.com/api/v1/dev/status/

# Credit an account. This also marks it a test account: everything it buys
# from here on is flagged and never reaches revenue or a sale alert.
curl -X POST -H "X-Admin-Test-Token: $TOKEN" -H "Content-Type: application/json" \
     -d '{"email":"qa@esimsterr.com","amount":"25"}' \
     https://esimsterr.com/api/v1/dev/balance/

# Settle an order outright. provision=false stops before the provider.
curl -X POST -H "X-Admin-Test-Token: $TOKEN" -H "X-Support-Id: ESM-QA11-QA22" \
     -H "Content-Type: application/json" \
     -d '{"plan_id":529,"email":"qa@esimsterr.com","consent":true,"provision":true}' \
     https://esimsterr.com/api/v1/dev/complete/
```

### Test orders never count

An order is flagged `is_test` when the buyer is a test account or the admin tool
settled it. Flagged orders send no sale alert, report no `purchase` event, and
are filtered in the admin. An operator who stops trusting the revenue figure
stops reading the alerts, and then misses a real failure.

## A live key cannot be used from a development run

Testing the in-app payment endpoint against a throwaway SQLite database once put
a real $4.99 PaymentIntent on the live Stripe account. No money moved and it was
cancelled a minute later, but it sat in the dashboard with no matching order —
the order was in the scratch database and Stripe was not.

A live key now refuses to work when `DEBUG` is on or the database is SQLite:

    Refusing to use a live Stripe key when the database is SQLite.
    Use test keys (sk_test_…), or set STRIPE_ALLOW_LIVE_IN_DEBUG=True
    if you really mean to charge the live account from here.

Production is unaffected — it runs `DEBUG=False` against Postgres. If a
PaymentIntent ever appears in Stripe with no order behind it, this is the shape
of the cause: something pointed a live key at a database that is not the live
one.

## Staging

`render.yaml` defines `esimsterr-staging`. Create it from the Blueprint, then
fill the `sync: false` values:

- `STRIPE_SECRET_KEY` — `sk_test_…`
- `STRIPE_PUBLISH_KEY` — `pk_test_…`
- `STRIPE_WEBHOOK_SECRET` — from a webhook pointed at the staging host
- `YESIM_API_TOKEN` — the same one. Yesim has no sandbox, so provisioning there
  spends real provider balance. Buy the cheapest plan you can.
- `ADMIN_TEST_TOKEN` — if you want the tool there too

No `DB_*` variables, deliberately: with none set the app falls back to SQLite on
the instance disk, which Render wipes on every deploy. Each deploy starts from a
clean catalogue and no accounts, so a test never inherits yesterday's mess.

`SEO_NOINDEX=True` puts `noindex,nofollow` on every page and makes robots.txt
disallow everything. A test environment in a search result competes with the
real site for its own keywords and shows customers prices that are not for sale.

Build the app for it: `./gradlew :app:assembleStaging`. It installs alongside
the real app with its own id, so one phone can hold both.

### Stripe test cards

| Card | What it does |
|---|---|
| 4242 4242 4242 4242 | Succeeds |
| 4000 0025 0000 3155 | Requires 3D Secure |
| 4000 0000 0000 9995 | Declined, insufficient funds |
| 4000 0000 0000 0002 | Declined, generic |

Any future expiry, any CVC, any postcode.

## The checks, and what they should do

Cheapest plans for provisioning: Turkey `501 MB / 1 day` (id 529, €0.32
wholesale) and `1 GB / 7 days` (id 530, €0.50).

1. **Buy with nothing but a device id.** No account, no sign-in. The order binds
   to the app installation, and My eSIMs shows it afterwards. Another device
   must see nothing.
2. **Register, verify, top up, buy from balance.** Registration returns no
   session until the emailed link is opened; signing in before that is refused
   with `email_unverified`.
3. **Coupons.** `WELCOME10` is 10% and first-order-only. `BORDERLESS20` is 20%
   and needs $9.99. A wrong code, a second use and an order under the minimum
   must all be refused with a reason a customer could act on.
4. **The ledger.** After any sequence, `SUM(wallet transactions)` must equal the
   wallet balance. If it does not, stop and find out why before shipping.

### Last run

Against production, 15 September 2026, using the admin tool:

| Check | Result |
|---|---|
| Guest device purchase, real provisioning | Pass — `ES-SE8VT2G`, ICCID issued, LPA present |
| Device reads back its own order | Pass — 1 order; another device saw 0 |
| Register → verify → sign in | Pass — 403 `email_unverified` before verifying |
| Grant balance, buy from it | Pass — $20.00 → $18.51 on a $1.49 plan |
| `WELCOME10` on a first order | Pass — $1.49 → $1.34 |
| `BORDERLESS20` on a $10.99 plan | Pass — $10.99 → $8.79 |
| `BORDERLESS20` on a $1.49 plan | Correctly refused — under the $9.99 minimum |
| Reusing `WELCOME10` | Correctly refused — already used |
| Unknown code | Correctly refused |
| Ledger equals balance | Pass at every step |

Provider balance went €30.00 → €22.84 across those runs.
