# Policy plan

Written for the operator of eSIMsterr and whoever reviews this before the mobile
app ships. It is not legal advice, and the documents it describes are templates
that a lawyer in the selling entity's jurisdiction should read before the first
significant month of revenue.

## The three layers

Keeping these apart is what makes the system modular. Most legal debt comes from
mixing them: a retention period buried in a support macro, an enforcement rule
that exists only in one person's head.

**Layer 1 — published documents.** What the customer is shown and agrees to.
Versioned, hashed, acceptance recorded. Seven of them, in `apps/legal/`.

**Layer 2 — operating policies.** How the business behaves so that Layer 1 is
true. Internal, unversioned, this file. No customer reads them; every one of
them is a promise in Layer 1 that somebody has to keep.

**Layer 3 — records.** The evidence that Layer 2 happened: the acceptance
ledger, order fingerprints, the deletion log, Stripe's dispute evidence.

A change starts in whichever layer it belongs to and propagates outward. A new
payment provider is a Layer 2 decision that forces a Layer 1 edit to one
document — the sub-processor register — and nothing else.

## Layer 1: what is published

| Document | URL | Covers | Changes when |
|---|---|---|---|
| Terms of Service | `/terms/` | The contract | Pricing model, subscriptions, jurisdiction |
| Privacy Policy | `/privacy/` | Data handling | New data collected, new purpose |
| Refund Policy | `/refund-policy/` | Money back | Refund rules change |
| Acceptable Use | `/acceptable-use/` | How the line may be used | A new abuse pattern |
| Cookie Policy | `/cookie-policy/` | Every cookie | A measurement or support tool is added |
| Sub-processors | `/sub-processors/` | Who else touches data | A provider is added or swapped |
| App Licence | `/app-licence/` | The app itself | Store requirements change |

Terms, Privacy, Refund and Acceptable Use are `CONTRACT_DOCUMENTS`: buyers are
recorded as accepting those four, at that version, on every purchase.

The split is the point. Swapping Resend for another mail provider used to mean
editing the privacy policy — a document customers have accepted — for an
operational change that alters nobody's rights. Now it is one row in one table
on one page with its own version.

## Layer 2: the operating policies

Each one names what it guarantees in Layer 1, where it is actually enforced, and
how often to look at it.

### 1. Data retention
Guarantees the retention table in the privacy policy.
Enforced by `purge_fingerprints` (24 months, run daily from the catalogue cron)
and by `delete_account` on request. Review yearly, or when the card schemes
change their dispute window. **If you change `RETENTION_DAYS`, the privacy
policy is now wrong — change both.**

### 2. Account deletion
Guarantees "you can delete your account yourself" and Play's deletion
requirement. Enforced by `apps/accounts/deletion.py`, reachable at
`/dashboard/account/delete/` signed out, and at `POST /api/v1/account/delete/`
in the app. Cancels Stripe billing *first*, and refuses to proceed if it cannot
— a closed account with a live subscription is a customer being charged with no
way left to stop it. Test after any subscription change.

### 3. Subject requests (access, export, correction, objection)
Guarantees "email us and we will action it within 30 days".
Today this is manual: read the order and support tables, answer by email. That
is fine at this volume and stops being fine at roughly one request a week —
that is the trigger to build an export endpoint, not a date.

### 4. Fraud and chargeback defence
Guarantees the fraud clause. The fingerprint is captured at checkout, the
evidence goes to Stripe when a dispute opens, and it is deleted at 24 months.
Policy: never use the fingerprint for anything but fraud, disputes and abuse.
The moment it is used to segment a marketing list, the lawful basis stated in
the privacy policy is false.

### 5. Acceptable use enforcement
Guarantees the AUP. Suspension ladder: contact, suspend the line, close the
account, report where the law requires it. No refund on suspension for breach.
Log the reason on the order or account so a reversal is possible — we say in the
AUP that we will restore a line we got wrong, and that needs a record.

### 6. Abuse reports from carriers
Answer within one business day. Keep the report, the line, and the action taken.
This is what protects the whole IP range the other customers are on.

### 7. Law enforcement requests
Policy: nothing is handed over without valid legal process from a jurisdiction
that binds the entity. Verify the requester, produce only what the request
covers, log it. We hold no traffic content, so most requests can only be
answered with an order record — say so rather than volunteering more.

### 8. Incident response
If personal data is breached and there is a risk to people: contain, assess,
notify the supervisory authority within 72 hours of becoming aware, notify
affected customers, write it down. The privacy policy now promises this, so the
contact point for the authority has to be known **before** it is needed.

### 9. Sub-processor management
Before a new provider touches customer data: check its terms, confirm the
transfer safeguard, add it to the register, bump that document's version. In
that order. The register is the Layer 1 artefact of this policy.

### 10. AI assistant conduct
Guarantees the assistant clauses. The model may not issue refunds, close
accounts or change orders; it quotes catalogue figures character for character
and runs at temperature 0. Conversations are reviewable by support, deleted with
the account. If the model is ever changed, re-check that Anthropic's commercial
no-training term still holds and update the sub-processor register.

### 11. Marketing consent
Product email is consent-based and separately withdrawable. Transactional email
is not marketing and is sent regardless. Do not merge the two lists; that single
shortcut is most of what makes a small shop non-compliant.

### 12. Pricing claims
The struck-through figure is anchored to wholesale cost times a market
multiplier, never to a price we previously charged, and the terms say so. If
that anchor ever becomes "our old price", the terms clause becomes false and the
claim becomes a misleading-pricing problem in the EU and the UK.

## Layer 3: the records

| Record | Where | Kept |
|---|---|---|
| Acceptance ledger | `legal_legalacceptance` | While the contract can be disputed |
| Order fingerprint | `orders_order` | 24 months, purged automatically |
| Deletion log | application log | Ordinary log retention |
| Dispute evidence | Stripe | Stripe's own retention |
| Version lock | `apps/legal/versions.lock.json` | Git history, for ever |

## What forces a change

| Event | Do this |
|---|---|
| Add or swap a provider | Sub-processors: new version, effective date, history entry |
| Ship the mobile app | Set `APP_STORE_URL`/`PLAY_STORE_URL`; the EULA becomes listed and app clauses appear |
| Start advertising | Cookie policy + a consent banner, **before** ad signals are enabled |
| Register for VAT/sales tax anywhere | Terms: prices and payment clause; invoice content |
| Incorporate, or move entity | `COMPANY_LEGAL_NAME`, `LEGAL_JURISDICTION`, `LEGAL_COURTS`, `COMPANY_ADDRESS` |
| Add a new data field to checkout | Privacy: what we collect, and the retention table |
| Change the retention window | `RETENTION_DAYS` **and** the privacy policy together |
| A new abuse pattern | Acceptable use: new version; usually not material |
| Change the AI provider | Privacy assistant clause + sub-processors |

## Calendar

**Daily** — abuse reports and support within one business day.
**Monthly** — read the acceptance ledger for gaps; confirm `purge_fingerprints`
ran; skim disputes for a pattern that is really a product problem.
**Quarterly** — reconcile the sub-processor register against what the code
actually calls; re-read the retention table against the code.
**Yearly** — full review of all seven documents; confirm the jurisdiction clause
still matches where the entity is; check store requirements have not moved.
**On every deploy** — `check_legal` (already wired into `build.sh`).

## Open decisions

These need the operator, not the code:

1. **The selling entity.** `COMPANY_LEGAL_NAME` is "Sterr Technologies" and
   `LEGAL_JURISDICTION` defaults to Türkiye. If the registered entity is
   somewhere else, the governing-law clause is unenforceable as written.
2. **Registered address.** `COMPANY_ADDRESS` is empty, so the imprint block is
   omitted rather than printed wrong. EU distance selling expects a contactable
   postal address; supply it before EU volume matters.
3. **VAT / sales tax.** Not addressed anywhere yet. Prices are stated as
   inclusive of our margin, silent on tax. Selling digital services to EU
   consumers eventually triggers VAT-OSS registration; the trigger is revenue,
   so decide the threshold at which you deal with it.
4. **Consumer withdrawal wording.** The terms rely on the customer consenting to
   immediate supply and thereby losing the 14-day withdrawal right. That consent
   should be an explicit checkbox at checkout in the EU, not an implied
   acceptance. It is currently implied.
