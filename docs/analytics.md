# Analytics

Measurement ID `G-7F3NXHKXVT`, set through `GA_MEASUREMENT_ID`. Unset the
variable and every line of tracking disappears; nothing else breaks.

## How it is wired

Anything involving money is reported **from the server**, not the browser. A
`purchase` event assembled in JavaScript can be replayed by a refresh, blocked
by an extension, or edited in devtools, and each of those quietly corrupts the
revenue report. So a view declares the events it wants in `analytics_events`,
`apps/common/analytics.py` shapes them into GA4's structure, and `base.html`
emits them once after the page has loaded.

Two things stay in the browser, because only the browser can see them: which
plan card was clicked, and what was typed into the destination search.

`purchase` fires exactly once per order. `Order.analytics_sent` flips in the
same request that emits it, so a refreshed or shared confirmation page reports
nothing. Verified by loading the same confirmation three times: one event, then
none.

## Events

| Event | Fires on | Carries |
|---|---|---|
| `view_item_list` | Home, country, region, unlimited | Up to 20 plans with prices |
| `select_item` | Clicking a plan card | The plan clicked, and which list it came from |
| `view_item` | Available for a single-plan page | Plan and price |
| `begin_checkout` | Checkout page, and the subscribe confirm page | Plan, price after coupon, coupon code |
| `add_payment_info` | Pressing pay | Adds `payment_type`: card or crypto |
| `purchase` | Order confirmation, once | `transaction_id` = order ref, value actually charged, coupon |
| `refund` | Available for the admin refund path | Order ref and value |
| `sign_up` | After registering | `method`: email or google |
| `login` | After signing in | `method`: email or google |
| `search` | Destination search, once the typing settles | `search_term` |
| `generate_lead` | Opening a support ticket | `lead_source` |

`sign_up` and `login` both end in a redirect, so the event is parked in the
session and emitted on the next page. It is popped when read, so it cannot
repeat.

Item fields are filled so the standard reports slice usefully with no extra
configuration:

- `item_category` — country, region, or topup
- `item_category2` — the destination name, so you can see which countries sell
- `item_category3` — the data size, or `unlimited`
- `item_variant` — the duration, e.g. `30d`, or `30d-subscription`

## What to set up in GA4

1. **Mark the conversions.** Admin, Events. Turn on "Mark as key event" for
   `purchase`, `begin_checkout`, `sign_up`. GA4 does not do this automatically
   for anything but `purchase` on some property types.

2. **Build the purchase funnel.** Explore, Funnel exploration, with these steps:

   | Step | Event |
   |---|---|
   | 1 | `view_item_list` |
   | 2 | `select_item` |
   | 3 | `begin_checkout` |
   | 4 | `add_payment_info` |
   | 5 | `purchase` |

   Set it to open funnel. The gap between step 4 and step 5 is the one to watch:
   people who chose a payment method and did not finish are either hitting a
   payment failure or balking at the redirect.

3. **Build the account funnel**: `session_start`, `view_item_list`, `sign_up`.
   Most buyers check out as guests, so a low rate here is expected and fine. It
   is worth watching only if you later make an account compulsory.

4. **Breakdowns worth saving as reports.**
   - Revenue by `item_category2` — which destinations actually sell.
   - Revenue by `item_category3` — whether people buy small plans or unlimited.
   - `add_payment_info` by `payment_type` — the real card-versus-crypto split,
     which decides whether the crypto integration is worth its fees.
   - `search_term` with no matching purchase — destinations people want that we
     do not sell well, or spellings our search does not match.

5. **Leave advertising signals off** unless you start running ads. Consent Mode
   is initialised with `ad_storage`, `ad_user_data` and `ad_personalization` all
   denied, and `anonymize_ip` on. If you do start advertising, that is the
   moment to add a consent banner, not before: turning the signals on without
   asking is what makes a site non-compliant in the EU.

## Sanity checks

Use GA4's DebugView with the GA Debugger extension, or append `?_dbg=1` and
watch the Network tab for requests to `google-analytics.com/g/collect`.

Expected on a full journey: `view_item_list` on a country page, `select_item`
on the plan click, `begin_checkout` on the checkout page, `add_payment_info` on
submit, `purchase` on the confirmation, and nothing at all on a refresh of that
confirmation.
