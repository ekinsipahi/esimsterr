# App store readiness

Written for whoever prepares the iOS and Android submissions. It covers only the
legal and policy surface — not the app build. Nothing here needs to be done
today; it exists so that shipping the app is a checklist rather than a rewrite.

## The one question that decides everything

The app does not take payment. `POST /api/v1/checkout-url/` returns a web URL
that the app opens in the system browser, and the customer pays there. Whether
that is allowed turns on how the store classifies an eSIM data plan.

**The position to take:** a mobile data plan is a service consumed outside the
app, not digital content unlocked inside it — the same category as a physical
SIM or a carrier plan. Apple's rules for goods and services outside the app
permit external payment for these. This is how every other travel eSIM app on
the store operates.

**What that position obliges you to do**, and what the code already does:

- The app must not read as a storefront that happens to check out elsewhere. It
  is a management tool: your lines, your data balance, your QR codes, support.
- No in-app purchase flow, no price-comparison screen that exists only to funnel
  to the web, no "cheaper on our website" messaging inside the app.
- Nothing is gated behind buying. The catalogue is public.

Guideline numbers move between store review cycles. Re-read the current text of
Apple's "Payments" section and Google Play's Payments policy the week you submit
rather than trusting any number written here.

## Apple: what review asks for

| Requirement | Status |
|---|---|
| Privacy policy URL | `https://esimsterr.com/privacy/` — public, no login |
| Custom EULA URL | `https://esimsterr.com/app-licence/` — carries Apple's minimum terms |
| Apple not a party; Apple a third-party beneficiary | In the EULA, iOS surface only |
| Apple's sole warranty remedy is a refund of the app price | In the EULA warranty clause |
| In-app account deletion | `POST /api/v1/account/delete/`, plus the web page |
| Privacy nutrition label matches the policy | Table below |
| Sign in with Apple, if third-party sign-in is offered | **Not built.** Google sign-in exists, so this is required |
| Age rating | 17+ is unnecessary; the terms set a minimum age of 16 |
| Demo account for review | Create one before submitting; review will not buy a plan |

**Sign in with Apple is the one real gap.** An iOS app offering Google sign-in
must also offer Apple's. It is an authentication change, not a legal one, but it
blocks submission.

## Google Play: what the console asks for

| Requirement | Status |
|---|---|
| Privacy policy URL | `https://esimsterr.com/privacy/` |
| Account deletion URL, reachable without installing the app | `https://esimsterr.com/dashboard/account/delete/` — renders signed out on purpose |
| Data safety form matches the policy | Table below |
| Payments policy | Same external-service position as Apple |
| Target audience | Adults; no children's category |

## The disclosure table

Both stores ask the same questions in different words. These answers come from
the privacy policy's app clause, and the two must never disagree — that is why
the app clauses live in the same clause library as the web ones.

| Data | Collected | Linked to you | Used for tracking | Why |
|---|---|---|---|---|
| Email address | Yes | Yes | No | Account, delivery, receipts |
| Purchase history | Yes | Yes | No | Your orders and eSIM lines |
| Support content | Yes | Yes | No | Answering you |
| Device / OS version | Yes, with crash reports | No | No | Diagnostics |
| Push token | If you allow notifications | No | No | Delivery and renewal alerts |
| Payment info | **No** | — | — | Purchases happen on the website |
| Precise location | **No** | — | — | Never collected |
| Contacts, photos, calendar, microphone | **No** | — | — | Never requested |
| Advertising identifier | **No** | — | — | No advertising SDK |

Because no advertising identifier is collected and nothing is shared for
cross-app tracking, the App Tracking Transparency prompt is not required. Adding
any analytics SDK that collects an advertising identifier changes that answer,
the nutrition label, the cookie policy and the privacy policy at once.

## Before the first submission

1. Set `APP_STORE_URL` / `PLAY_STORE_URL`. The EULA then appears in the footer
   and in `/legal/`, and app-surface clauses go live.
2. Build Sign in with Apple.
3. Preview every document as the app will compose it:
   `/terms/?surface=ios`, `/privacy/?surface=ios`, `/app-licence/?surface=android`
   (staff only). Read the iOS terms in particular — two clauses appear that the
   web version does not have.
4. Confirm the app renders legal text from `GET /api/v1/legal/<slug>/` rather
   than bundling its own copy. A policy inside a binary cannot be corrected
   without a store review.
5. Wire the launch check: compare `config.legal` stamps against what the
   customer last accepted, show the changed document, and `POST
   /api/v1/legal/accept/` when they acknowledge it.
6. Create the review demo account, with an eSIM line on it that has usage, so
   the dashboard is not empty.
7. Re-read both stores' current payment rules.

## After launch

The sub-processor register grows by two entries — Apple and Google, for push
notification delivery — if push is enabled. That is a version bump on one
document and nothing else, which is the whole point of the split.
