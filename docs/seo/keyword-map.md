# eSIMsterr keyword map

Companion file: `docs/seo/raw-keywords.txt` (647 unique terms, grouped by intent, one per line).
This document is the plan; the raw file is the working list that gets diffed and re-imported.

All volumes and CPCs quoted here come from the owner's export. Terms marked
"(expanded, no volume data)" were reconstructed from the export's family patterns and
must be volume-checked before any of them is promoted to a page of its own.

---

## 0. Inventory snapshot

Everything below is measured against what the catalogue actually contains today. Numbers
were read from the live database, not estimated.

| Fact | Value |
| --- | --- |
| Active countries (`/esim/<slug>/`) | 148 |
| Active regions (`/esim-region/<slug>/`) | 9 |
| Live plans (`Plan.objects.live()`) | 1,560 |
| Lowest price on the site | $1.49 |
| Lowest unlimited plan | $6.99 |
| Countries with an unlimited option | 100 of 148 |
| Countries whose entry price is $2.00 or less | 90 of 148 |
| Countries by continent | Europe 44, Americas 39, Asia 39, Africa 22, Oceania 4 |
| Europe region coverage | 33 countries in one eSIM |
| Published blog posts | 3 |
| Countries with a written `intro` | **0 of 148** |
| Countries with a written `seo_title` | **0 of 148** |
| Countries with a written `seo_description` | **0 of 148** |

That last block is the single biggest risk in the whole plan and it is dealt with in
section 3.4. Right now all 148 country pages render the same fallback paragraph and the
same four templated FAQ answers with only the country name swapped. That is the textbook
shape of a doorway cluster, and we are doing it at scale before we have done it once well.

---

## 1. Strategy summary

We sell the same wholesale data as the big eSIM apps at a lower retail price, because we
do not buy app-install advertising and they do. That is not a slogan, it is the entire
strategic asset: a competitor whose customer acquisition cost is loaded into every plan
cannot answer "cheap esim" honestly without cutting the budget that keeps them alive, so
price-intent search is the one battlefield where our unit economics beat theirs. We
therefore take two beachheads and ignore everything else until they are held: **price
intent** (`cheap esim`, 8.1K, $5.63 CPC) served by one strong hub plus real prices in
every title, and **transactional destination intent** (`buy esim <place>`, hundreds of
variants against 148 countries we can actually provision today).

The brand frame - freedom, no borders, no roaming rip-off - is what keeps this from
reading as a discount-bin site. We lead with the price because it is true and checkable,
and we back it with plain explanations of what the plan does. Price is the hook, honesty
is the retention.

---

## 2. Intent taxonomy

Every keyword family sits in exactly one primary intent. A term that could sit in two
(for example `esim satin alma`, which is both destination-transactional and Turkish) is
filed under its primary intent in `raw-keywords.txt` and cross-referenced in a comment.

| Intent | Representative keywords | Canonical page type | URL pattern | Template | The page's conversion job | Coverage today |
| --- | --- | --- | --- | --- | --- | --- |
| Transactional-destination | buy esim italy, esim turkey, buy esim canada (260), buy esim for europe (260) | Destination product page | `/esim/<country-slug>/`, `/esim-region/<region-slug>/` | `catalog/country_detail.html`, `catalog/region_detail.html` | Put the cheapest suitable plan for that place in front of a buyer who has already decided where they are going | 148 + 9 pages exist; all thin |
| Transactional-price | cheap esim (8.1K), cheapest us esim (260), cheap esim plans usa (260, $17.84) | Price hub + priced destination pages | `/cheap-esim/` | new, reuse `catalog/destinations.html` shape | Prove in one screen that we are the cheapest credible option, then hand off to a destination page | **Missing** |
| Transactional-payment | buy esim with crypto, buy esim with bitcoin, buy esim with usdt | Single payment landing page | `/buy-esim-with-crypto/` | new `pages/` template | Remove the "can I even pay this way" objection and route straight to checkout | **Missing** |
| Deal/coupon | esim sale (480), cheap esim deals (260), esim discount code, esim promo code | Offer hub, max three children | `/coupons/`, `/coupons/<offer>/` | being built | Convert a discount-hunter now rather than losing them to a coupon aggregator | Hub in progress |
| Comparison/alternative | airalo alternative, saily alternative, esim saily (9.9K) | Comparison page, one per major competitor | `/alternatives/<brand>/` | new `pages/` template | Win the shopper who has a competitor's app open by showing the same data at a lower price | **Missing** |
| Informational-education | esim explained (480), what is an esim, esim vs physical sim | Evergreen explainer | `/what-is-an-esim/`, `/how-it-works/`, `/faq/`, `/blog/<slug>/` | `pages/how_it_works.html`, `blog/detail.html` | Turn a first-time eSIM buyer into someone who trusts the format, then into a first order | `/how-it-works/`, `/faq/`, 3 posts exist; no `/what-is-an-esim/` |
| Informational-troubleshoot | esim not working (2.4K), esim no service, esim qr code not working | Diagnostic page | `/esim-not-working/` | promote existing blog post | Fix the problem, keep the customer, and capture a large pre-purchase audience that is researching failure modes | Exists only as `/blog/esim-not-working-checklist/` |
| Compatibility | cheap esim compatible phones (320), is my phone esim compatible | Device checker | `/esim-compatible-devices/` + anchors | `pages/devices.html` | Answer "will this work on my phone" so the buyer proceeds instead of abandoning | Page exists, thin for the keyword |
| Local-adjacent / sim-only | cheap sim only deals (27.1K), cheap sim card turkey, cheap sim istanbul | Mostly not ours; the traveller subset is a blog post plus a country-page section | `/blog/<slug>/`, section on `/esim/<slug>/` | `blog/detail.html` | Intercept only the travellers inside a domestic-contract keyword set | Not covered, mostly deliberate |
| Non-English | esim satin alma (390), esim ucuz, esim sale sin servicio | Translated locale, not translated slugs on English text | `/tr/...`, `/es/...` via Django i18n | existing templates under a locale prefix | Serve Turkish and Spanish demand in their own language or not at all | **Missing, and blocked until translations are real** |

### Pages that must be created

`/cheap-esim/`, `/buy-esim-with-crypto/`, `/what-is-an-esim/`, `/esim-not-working/`,
`/alternatives/airalo/`, `/alternatives/saily/`, `/alternatives/holafly/`, and at most
three children under `/coupons/`. That is eleven new URLs in total. Everything else in
this plan is improvement of pages that already exist.

### Pages that must NOT be created

`/buy-esim/` - the head term `buy esim` (9.9K) belongs to the homepage. A separate
`/buy-esim/` page would compete with `/` for the same query with the same content and
split the signal. Same reasoning rules out `/esim-deals/` alongside `/coupons/`, and
`/cheapest-esim/` alongside `/cheap-esim/`.

---

## 3. The page plan

Waves are ordered by volume divided by effort. Wave 1 is almost entirely fixing pages
that already exist, which is why it ships first.

### 3.1 Wave 1 - ship first

| URL | Primary keyword | Secondary keywords | Intent | The page's single job | Minimum unique content | Links in | Links out |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `/cheap-esim/` (new) | cheap esim (8.1K, $5.63) | cheapest esim, cheap esim deals (260), cheap esim app (720), cheap esim plans | Transactional-price | Prove the price claim in one screen and route to a destination | Live table of the 10 cheapest plans on the site with price, price per GB, price per day and destination; a 120-word plain explanation of why we are cheaper (no app-install ads, no retail packaging, thin margin by design); a price-floor-by-region table built from `Region.min_price_usd`; six FAQ entries on what the low price does and does not include | Header nav, homepage hero, footer, price section of every country page | Top 12 country pages, `/unlimited-esim/`, `/coupons/`, `/how-it-works/` |
| `/` | buy esim (9.9K, $7.00) | travel esim, esim for travel | Transactional-destination | Entry point and price hook | Add `from just $1.49` to the title and hero; keep the destination search as the primary action | External, brand search | `/cheap-esim/`, `/destinations/`, `/regions/`, top destinations |
| `/coupons/` | esim sale (480, $4.50) | cheap esim deals (260), esim discount code, esim promo code, esim on sale | Deal/coupon | Convert a discount hunter before they leave for a coupon aggregator | Live offer table with code, what it does, minimum spend and expiry; a plain statement when there is no active code; how the referral credit works; last-updated date | Footer, checkout page, `/cheap-esim/`, country-page offer strip | `/cheap-esim/`, top destinations |
| `/esim-not-working/` (promote existing post, 301 the blog URL) | esim not working (2.4K, $2.25) | esim installed but no internet, esim no service, esim qr code not working | Informational-troubleshoot | Fix the fault, and be the page that earns trust before purchase | The existing checklist, reordered by actual failure frequency; a per-symptom decision list; the APN values we issue; a direct link into `/support/` with the ICCID field pre-explained | `/support/`, `/faq/`, install emails, dashboard eSIM page | `/support/`, `/esim-compatible-devices/`, `/faq/` |
| 20 popular country pages | buy esim `<country>`, cheap esim `<country>` | esim `<country>` price, `<country>` esim, buy esim online `<country>` | Transactional-destination | Sell the cheapest suitable plan for that destination | See 3.4 - written `intro`, written meta, a real local fact, one country-specific FAQ | `/destinations/`, `/cheap-esim/`, region pages, nearby-country modules | Their region page, `/esim-compatible-devices/`, `/how-it-works/` |
| All 157 destination pages (template change) | - | - | Transactional-destination | Carry the price into the SERP | Roll out the title and description patterns in section 4 so every snippet shows `from just $X` | - | - |

### 3.2 Wave 2

| URL | Primary keyword | Secondary keywords | Intent | The page's single job | Minimum unique content | Links in | Links out |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `/buy-esim-with-crypto/` (new) | buy esim with crypto | buy esim with bitcoin, buy esim with usdt, esim pay with crypto | Transactional-payment | Remove the payment objection and go straight to checkout | Which coins we settle (NOWPayments), what confirmation time looks like, what happens if the rate moves between quote and settlement, what we do and do not store, and an explicit note that no phone number or identity document is involved because the plans are data-only | `/how-it-works/`, checkout, footer | `/cheap-esim/`, top destinations |
| `/what-is-an-esim/` (new) | esim explained (480, $1.34) | what is an esim, how does an esim work, esim vs physical sim, esim is good or bad | Informational-education | Convert a first-time eSIM buyer's uncertainty into a first order | 700-900 words written once and properly; a physical SIM versus eSIM comparison table; what "data-only" means for calls and WhatsApp; the dual-SIM explanation; what does not work (no voice number, no smartwatch provisioning) | `/how-it-works/`, `/faq/`, blog posts, homepage | `/esim-compatible-devices/`, `/cheap-esim/`, `/how-it-works/` |
| `/esim-compatible-devices/` | cheap esim compatible phones (320, $3.59) | esim compatible phones list, is my phone esim compatible, cheap esim android phone | Compatibility | Let a buyer confirm their handset in under ten seconds | Searchable device list from the `Device` model; the carrier-lock caveat, which is the actual reason most "compatible" phones fail; per-brand anchors for Apple, Samsung, Google and Motorola; tablet section | `/what-is-an-esim/`, every country page, `/esim-not-working/` | `/cheap-esim/`, `/esim-not-working/` |
| `/unlimited-esim/` | cheap unlimited esim europe | cheapest esim unlimited data uk, cheap sim only deals unlimited data (traveller slice only) | Transactional-price | Sell the unlimited tier honestly, including its limits | State the fair-use position plainly; list the 100 countries where unlimited exists; show the $6.99 entry price; explain when a capped plan is the cheaper answer, which is most short trips | Homepage, `/cheap-esim/`, country pages with `has_unlimited` | Country pages, `/cheap-esim/` |
| 9 region pages | buy esim europe, cheap esim asia | cheap esim eu, buy esim south east asia, cheap esim middle east | Transactional-destination | Sell one eSIM for a multi-country trip | Per region: which countries are in and, more usefully, which popular neighbours are out; a worked cost comparison against buying two or three country plans; the border-crossing behaviour | `/regions/`, member country pages, homepage | Member country pages, `/cheap-esim/` |
| 40 tier-2 country pages | buy esim `<country>` | cheap esim `<country>` | Transactional-destination | As Wave 1 countries | Written `intro` and meta per 3.4 | `/destinations/`, region pages | Region page, `/esim-compatible-devices/` |
| `/alternatives/airalo/`, `/alternatives/saily/`, `/alternatives/holafly/` (new, three only) | airalo alternative, saily alternative, holafly alternative | cheaper than airalo, esim provider comparison, best cheap esim provider | Comparison/alternative | Win the shopper who already has a competitor's app open | A like-for-like price table for five identical plan shapes on the same destinations, with the comparison date shown; an honest statement of what the competitor does better; no unverifiable claims and no scraped prices presented as current | `/cheap-esim/`, blog | `/cheap-esim/`, destination pages |

### 3.3 Wave 3

| URL | Primary keyword | Secondary keywords | Intent | The page's single job | Minimum unique content | Links in | Links out |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Remaining 88 country pages | buy esim `<country>` | cheap esim `<country>` | Transactional-destination | As above | Written `intro` per 3.4, or the demotion rule in 3.4 applies | `/destinations/`, region pages | Region page |
| `/tr/` locale, top 20 pages | esim satin alma (390, $2.13) | esim ucuz, esim japonya, esim nedir, yurt disi esim | Non-English | Serve Turkish demand in Turkish | Genuine Turkish translation of home, `/cheap-esim/`, `/what-is-an-esim/` and the 15 destinations Turkish travellers actually buy; Turkish-language support reply capability before launch, not after | Language switcher, hreflang | Turkish destination pages |
| `/es/` locale, troubleshooting first | esim sale sin servicio | no me sale esim en iphone, porque sale esim no compatible, comprar esim barata | Non-English | Serve Spanish troubleshooting and price demand | Spanish `/esim-not-working/` equivalent first, because that is where the Spanish volume sits; then the price hub | Language switcher, hreflang | Spanish destination pages |
| 6 blog posts | how much data do i need abroad, esim vs roaming, tourist sim card vs esim, cheap sim only deals for travel | long-tail education and comparison | Informational-education | Feed the destination pages with topical links and capture research intent | 900+ words each, one original calculation or dataset per post, no listicle padding | `/blog/`, `/what-is-an-esim/` | Destination pages, `/cheap-esim/` |
| `/destinations/` | buy esim online `<country>` (aggregate) | esim destinations, travel esim countries | Transactional-destination | Be a usable index, not a link dump | Sortable price column from `min_price_usd`, continent grouping, an unlimited-available filter | Header, homepage, footer | All country pages |

### 3.4 The 148 country pages and 9 region pages

This is where the plan either works or gets us classified as scaled content abuse.

**The current state.** All 148 countries have an empty `intro`, `seo_title` and
`seo_description`. Every page therefore renders the identical fallback paragraph
("Prepaid data for X on the local networks...") and the identical four templated FAQ
answers. The only genuinely varying content is the plan grid, the operator chips and the
price floor. Against a competitor with hand-written destination pages, this loses.

**What differs today and can be leaned on.** Plan counts range from 8 to 14 per country;
price floors range from $1.49 to $7.99; 100 countries have unlimited and 48 do not;
operator lists are real per-country data. That is enough to make each page factually
distinct, but facts in a table are not enough on their own - the prose has to differ too.

**Minimum unique content per country page.** A country page is not shippable as a target
until it has all six:

1. **A written `intro` of 60 to 90 words**, unique to that country, naming the actual
   partner networks from `operators`, the real price floor, and one concrete local fact a
   traveller would recognise. "Vodafone and Turk Telekom both cover the Istanbul metro,
   which is where most visitors first notice a dead SIM" is a fact. "Stay connected in
   beautiful Turkey" is filler and fails this rule.
2. **A written `seo_title` and `seo_description`** following section 4, hand-checked for
   the nine country names longer than 18 characters where the brand suffix must be dropped.
3. **A roaming cost comparison with a real number** for that destination, so the page
   answers "versus what" rather than asserting cheapness.
4. **The networks block**, which is already data-driven. Keep it.
5. **One country-specific FAQ entry** replacing one of the four templated ones. The
   remaining three templated entries are acceptable because they answer genuinely
   universal questions, but four out of four identical across 148 pages is not.
6. **A distinct plan grid**, which already exists.

**The demotion rule.** Until a country has a written `intro`, it stays indexed but is
removed from the "popular destinations" and "nearby countries" internal-link modules, so
we do not spend crawl budget and internal link equity promoting our thinnest pages. Any
country page that still has no written `intro` after Wave 3 and has recorded zero clicks
and fewer than 50 impressions in 180 days gets `noindex`, not another templated paragraph.
Shipping 88 near-duplicates is worse than shipping 60 good pages.

**Region pages** already have written descriptions, so their gap is narrower: each needs
the cost comparison against buying the equivalent country plans separately, and an explicit
list of popular countries the region does *not* cover. That second item is the most useful
thing a region page can say and no competitor says it.

---

## 4. Title and meta patterns

**Hard limits.** Title: 60 characters maximum, measured in characters as the working
proxy for pixel width. Description: 155 characters maximum. Both are enforced in the view
or template, not left to whoever writes the copy. Every example below has been
length-checked and the count is shown.

**Rules that apply to every pattern.**

- The price hook is not optional on commercial pages. Our whole edge is price, so the
  number goes in the title where it is visible in the SERP.
- The price is always rendered from `min_price_usd` or `Plan.price`, never hard-coded. If
  the wholesale price moves, the title moves with it and stays true.
- Brand suffix ` | eSIMsterr` is dropped whenever the rest of the title exceeds 48
  characters. Nine country names trigger this.
- No exclamation marks. No "best" or "#1" claims we cannot substantiate.
- The description repeats the price and adds one fact the title could not fit.

| # | Intent | Title pattern | Filled example | Len |
| --- | --- | --- | --- | --- |
| 1 | Destination (country) | `{Country} eSIM from just ${min_price} \| eSIMsterr` | Turkey eSIM from just $1.49 \| eSIMsterr | 39 |
| 2 | Destination, long name (>18 chars) | `{Country} eSIM from just ${min_price}` | Curaçao & Caribbean Netherlands eSIM from just $3.49 | 52 |
| 3 | Destination, buy-modifier variant | `Buy an eSIM for {Country} — from just ${min_price}` | Buy an eSIM for Canada — from just $1.99 | 40 |
| 4 | Price hub | `Cheap eSIM plans from just ${site_floor} \| eSIMsterr` | Cheap eSIM plans from just $1.49 \| eSIMsterr | 44 |
| 5 | Price plus place | `Cheapest eSIM for {Place} — from just ${min_price}` | Cheapest eSIM for the USA — from just $1.49 | 43 |
| 6 | Payment | `Buy an eSIM with {method} — from just ${site_floor}` | Buy an eSIM with crypto — from just $1.49 | 41 |
| 7 | Coupon hub | `eSIM discount codes and live deals \| eSIMsterr` | eSIM discount codes and live deals \| eSIMsterr | 46 |
| 8 | Comparison | `{Brand} alternative — same data, from just ${site_floor}` | Airalo alternative — same data, from just $1.49 | 47 |
| 9 | Education | `What is an eSIM? Plain-English guide \| eSIMsterr` | What is an eSIM? Plain-English guide \| eSIMsterr | 48 |
| 10 | Troubleshoot | `eSIM not working? Fix it in {n} steps \| eSIMsterr` | eSIM not working? Fix it in six steps \| eSIMsterr | 49 |
| 11 | Compatibility | `eSIM compatible phones — full device list \| eSIMsterr` | eSIM compatible phones — full device list \| eSIMsterr | 53 |
| 12 | Region | `{Region} eSIM — {n} countries from just ${min_price}` | Europe eSIM — 33 countries from just $1.49 | 42 |
| 13 | Unlimited | `Unlimited data eSIM from just ${min_unlimited} \| eSIMsterr` | Unlimited data eSIM from just $6.99 \| eSIMsterr | 47 |

### Description patterns

| Intent | Filled example | Len |
| --- | --- | --- |
| Destination | Buy a Turkey eSIM from just $1.49. 13 plans on Turk Telekom and Vodafone, QR code emailed in a minute, no roaming bill, no contract. | 132 |
| Price hub | Travel eSIMs from just $1.49 across 148 countries. We skip the app-install ads, so the saving lands on your price instead of our marketing. | 139 |
| Price plus place | The cheapest US travel eSIM we sell starts at $1.49. Compare price per GB and per day across 11 plans, then pay by card or crypto. | 130 |
| Payment | Pay for a travel eSIM in Bitcoin or USDT, from just $1.49. The QR code arrives by email as soon as the payment confirms on chain. | 129 |
| Coupon | Current eSIM discount codes, seasonal sales and the referral credit. Every offer here is ours and live, with the expiry date shown. | 131 |
| Comparison | An honest price comparison against Airalo, plan for plan. Same local networks, from just $1.49, because we do not buy app-install ads. | 134 |
| Education | What an eSIM is, how it differs from a physical SIM, and what it costs abroad. Five minutes, no jargon, no sales pitch. | 119 |
| Troubleshoot | eSIM installed but no internet? Work through data roaming, APN, line selection and reinstallation in order. Most cases clear in two minutes. | 140 |
| Compatibility | Check whether your phone or tablet takes an eSIM before you buy. Full Apple, Samsung, Google and Motorola lists, plus the carrier-lock trap. | 140 |
| Region | One eSIM for 33 European countries from just $1.49. Cross borders without swapping anything, unlimited options available. | 121 |
| Unlimited | Unlimited data travel eSIMs from just $6.99. No speed cap in the first tier, hotspot allowed, and the plan starts only when you land. | 133 |

### Note on the current implementation

`apps/catalog/views.py` currently builds the country title as
`"{name} eSIM — prepaid travel data from ${min} | eSIMsterr"`. For Turkey that is 56
characters, which fits; for United Arab Emirates it is 70 and gets truncated, and for
Curaçao & Caribbean Netherlands it is 81. Pattern 1 above is both shorter and carries the
price hook earlier, where it survives truncation on mobile.

---

## 5. Anti-spam rules

The instruction was to grow without becoming spammy. These are the rules that enforce it.
They are deliberately restrictive, because the failure mode here is not "too few pages",
it is a site-wide quality classification that takes six months to recover from.

**R1 - No page without a product behind it.** If a keyword implies something we cannot
sell or provision today, there is no page. This kills the PayPal page, the smartwatch
page, and every "buy esim `<other carrier>`" page.

**R2 - No page without 150 words written for that page.** Templated prose with a variable
swapped does not count toward the 150. This is the test that the 148 country pages
currently fail.

**R3 - One page per intent, not one page per phrasing.** `buy esim italy`,
`cheap esim italy`, `esim italy price` and `italy esim` are one intent and get one URL:
`/esim/italy/`. They are served by the title, the H1, the intro and the FAQ on that single
page. We never create `/cheap-esim-italy/` alongside `/esim/italy/`.

**R4 - Consolidate by default.** Before creating any page, answer: would this page show
the same plan grid as an existing page? If yes, it is a section with an anchor on the
existing page, not a new URL. This is why there is no `/buy-esim/`, no `/cheapest-esim/`
and no `/esim-deals/`.

**R5 - Internal link caps.** Maximum two automated link modules per page, maximum 12 links
per module, maximum 30 in-body internal links per page excluding header and footer. Links
must be contextual: the nearby-countries module stays filtered to the same continent, as it
already is. A page that needs a third link module needs better content instead.

**R6 - No spun or machine-generated prose.** No sentence templates with rotating
adjectives, no auto-generated "Top 5 things to do in `<country>`" filler, no AI-written
country intros shipped unread. Each `intro` is read by a human before it goes live.

**R7 - No competitor coupon pages.** We do not have Airalo or Saily codes, so a page
targeting `esim discount code airalo` can only disappoint the visitor and invite a brand
complaint. The comparison pages in Wave 2 are the honest version of this intent.

**R8 - Non-English means translated, not slug-swapped.** A Turkish URL with English body
copy is a doorway. `/tr/` ships when the pages are genuinely translated and support can
answer in Turkish, with correct `hreflang` both ways, or it does not ship.

**R9 - Claims must be checkable.** "From just $X" is always the live minimum price for
that page's scope. Comparison tables carry the date the prices were checked. No countdown
timers, no fake stock counters, no invented "was" prices - the pricing display was already
corrected once on this repo for exactly that reason and the same standard applies here.

**R10 - Crawl hygiene.** The existing `robots.txt` disallow list stays. Filtered and
parameterised catalogue URLs are never indexable. New pages enter `core/sitemaps.py`
only once they pass R2.

### Families we deliberately do not target

| Family | Example terms | Volume where known | Why we skip it |
| --- | --- | --- | --- |
| Domestic SIM-only contracts | cheap sim only deals, cheap sim only deals uk, cheap sim only plans, cheap sim only plans 365 days | 27.1K, 9.9K, 8.1K, 1K | These are UK and Australian residents shopping for a monthly domestic contract SIM. We sell prepaid travel data. The traffic would bounce, and chasing it drags our topical relevance away from travel eSIM, which is the thing we are trying to be known for. We take only the traveller slice with one blog post. |
| Other carriers' branded eSIM | buy esim jio, buy esim airtel, buy esim telstra, buy esim vodafone, can i buy jio esim online | not supplied | Navigational intent for a specific operator's own product. We cannot provision a Jio or Airtel eSIM, so we can never satisfy the query. Country pages already name the partner networks we ride, which is the honest version. |
| Competitor coupon terms | esim discount code airalo, esim saily coupon, esim saily discount code, airalo esim sale, holafly esim sale | not supplied | We have no codes for these brands. Any page here is bait, and at scale it is exactly the pattern that gets a site reclassified. |
| Competitor brand navigational | esim saily | 9.9K | The searcher wants Saily's app. We take only the `saily alternative` slice with a real price comparison, and leave the brand term alone. |
| Voice and phone-number eSIM | buy esim phone number with crypto, anonymous esim crypto | not supplied | Our plans are data-only. We do not sell a phone number, so this is a product we do not have. |
| Smartwatch eSIM | ee apple watch esim cost, cheapest esim watch, esim watch compatible | not supplied | We do not provision smartwatch eSIM profiles. Answering these would generate refunds. |
| Device retail | esim phones for sale | not supplied | We do not sell handsets. |
| Local physical retail | esim store near me | not supplied | We have no physical presence, and the SERP is a map pack we cannot enter. |
| Forum and UGC intent | cheapest esim japan reddit | not supplied | The result set is Reddit threads. A commercial page will not displace them and should not try. |
| Unsupported payment methods | buy esim with paypal, buy esim with revolut, buy esim with gcash | not supplied | The payment stack is Stripe plus NOWPayments. Promising PayPal creates failed checkouts and support load. If PayPal is ever added, this family moves to `target` in one edit. |
| Other operators' pricing | cuanto sale esim movistar | not supplied | The searcher wants Movistar's prices, not ours. |

All of these are present in `raw-keywords.txt` with `skip` in the action column, so the
decision is recorded rather than forgotten. Eighty-two of the 647 terms are marked `skip`.

---

## 6. Coupon keyword plan

The hub is `/coupons/`. The discipline here matters more than anywhere else, because
coupon keywords are the easiest place in the world to accidentally build 40 thin pages.

### Hub target terms

| Keyword | Volume | Handled by |
| --- | --- | --- |
| esim sale | 480, $4.50 | `/coupons/` H1 and title |
| cheap esim deals | 260, $3.81 | `/coupons/` section, cross-linked from `/cheap-esim/` |
| esim discount code | not supplied | `/coupons/` title and offer table |
| esim promo code | not supplied | `/coupons/` H2 and FAQ |
| esim coupon code | not supplied | `/coupons/` H2 |
| esim on sale | not supplied | `/coupons/` section |
| prepaid esim on sale | not supplied | `/coupons/` section |
| esim deals | not supplied | `/coupons/` H2 |
| travel esim discount | not supplied | `/coupons/` intro |

### What the hub needs

A live offer table with code, what it does, minimum spend, expiry date and a copy control.
A standing-offer block for discounts that need no code, because our everyday price is the
main offer. A plain statement when there is no active code - saying "no code is running
right now, our standing price is $1.49" is better for trust and for repeat visits than
inventing one. A visible last-updated date. And a short explanation of the referral
credit, which is genuinely ours: `User.referral_code` and `User.referred_by` already exist
in the data model, so the mechanic is real and not a marketing fiction.

### Child pages - maximum three, and only when the offer is durable

| URL | Target keyword | Why it earns a URL | What it needs |
| --- | --- | --- | --- |
| `/coupons/black-friday/` | esim black friday sale | Seasonal demand is large, concentrated and recurring, and the URL accrues history year over year | Never 404 it out of season. Out of season it shows the next sale window, last year's discount depth and the current standing price. In season it shows the live codes. |
| `/coupons/referral/` | esim referral code | A real mechanic backed by existing model fields, and it is a share-driven acquisition loop rather than a discount leak | How the credit works for both sides, where the user finds their code in the dashboard, the terms in plain language |
| `/coupons/first-order/` | esim first order discount | Only build this if a welcome code actually exists | The code, the eligibility rule, the expiry |

### Coupon pages we will not build

Per-country coupon pages (`/coupons/turkey/`), per-brand coupon pages
(`/coupons/airalo/`), and per-month pages (`esim promo code september 2026`). All three
patterns produce the same offer with the same content at a different URL, which is the
definition of scaled content abuse and the fastest way to lose the rest of the site with
it. The country-level version of this intent is a single offer strip on
`/esim/<slug>/` that reads the same live offer as the hub, plus a link to `/coupons/`.

---

## 7. Measurement

### Tracked per wave

- **Indexation.** Submitted versus indexed in Search Console, per page group (countries,
  regions, hubs, blog). A country group below 90 percent indexed means the content is thin,
  not that the crawler is slow.
- **Rankings.** A fixed head-term set: `buy esim`, `cheap esim`, `esim sale`,
  `esim not working`, `esim explained`, `cheap esim compatible phones`, plus
  `cheap esim <country>` and `buy esim <country>` for the 20 popular destinations.
- **Search Console per group.** Impressions, clicks, click-through rate and average
  position, grouped by URL prefix. Impressions move first and are the early signal.
- **Funnel per landing-page group.** Organic landing to checkout start to paid order, using
  `Order.status` transitions to `paid` and `completed`.
- **Margin, not just revenue.** `Order.margin_usd` per landing-page group. Because the
  entire position is price, the discipline is to confirm that cheap traffic still clears
  margin. Organic orders whose margin sits materially below site average mean the price
  hook is pulling the wrong plans, not the wrong people.
- **Non-brand share** of organic clicks. Brand search will rise on its own; the plan is
  only working if non-brand rises faster.
- **Coupon leakage.** Discount cost per order attributed to `/coupons/`, against the
  incremental orders it produced.

### What "working" looks like

**At 30 days.** Wave 1 pages are indexed. The title and description patterns are live on
all 157 destination pages. `/cheap-esim/` is indexed and ranking anywhere in the top 50
for `cheap esim`. `/esim-not-working/` is live with the blog URL 301'd, not competing.
Twenty popular country pages have written intros. Country-group impressions are measurably
above the pre-launch baseline, and at least one paid order is attributed to an organic
landing on a country page. Rankings at this stage are noise; indexation and impressions
are the signal.

**At 90 days.** `cheap esim` inside the top 20. `esim not working` inside the top 10,
which is realistic because the checklist is genuinely better than most of what ranks.
At least 20 tier-1 destinations inside the top 30 for `cheap esim <country>`. Non-brand
organic clicks at roughly three times the 30-day baseline. Organic conversion rate at or
above the site average - if organic converts materially worse, the price hook is attracting
researchers rather than buyers and the titles need the purchase modifier from pattern 3.
Country-page indexation above 90 percent.

**At 180 days.** `cheap esim` inside the top 10. `buy esim <country>` inside the top 10 for
at least 15 destinations. Organic is the largest non-direct channel by paid orders. Margin
per organic order within 15 percent of site average. No manual action, no page group below
40 percent indexation, and the demotion rule from 3.4 has been applied to whichever country
pages did not earn their place. If `cheap esim` is still outside the top 20 at 180 days,
the problem is authority rather than on-page work, and the next investment is links and
original data rather than more pages.

### The kill rule

Any page with zero clicks and fewer than 50 impressions at 180 days is consolidated into a
stronger page or set to `noindex`. Pages are not free; each one spends crawl budget and
dilutes the average. Removing the weakest ten percent of pages is a legitimate and often
the highest-return SEO action available, and it is the one most teams never take.
