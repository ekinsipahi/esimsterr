"""The assistant's brain: intent detection, live account context, system prompt
and the Anthropic call.

GROUND RULE: the assistant speaks only from real eSIMsterr facts. It never
invents a price, a country, a date or a promise -- a wrong answer here costs a
refund and a chargeback, not just goodwill. Anything it cannot answer honestly
goes to a human through the ticket system.

Keyword lists are English and Turkish: the owner is Turkish and a large share of
customers write in Turkish, and intent detection drives escalation, so missing a
Turkish "param gitti" would mean a payment complaint sitting unread.
"""
from __future__ import annotations

import json
import logging
import re
import urllib.request

from django.conf import settings

log = logging.getLogger(__name__)

_ANTHROPIC_URL = "https://api.anthropic.com/v1/messages"
_TIMEOUT = 20
_HISTORY_TURNS = 16


def _model() -> str:
    return getattr(settings, "ASSISTANT_MODEL", "") or "claude-haiku-4-5-20251001"


# --- Intent detection --------------------------------------------------------
_INTENT_KEYWORDS = {
    "install": (
        "install", "installing", "qr", "scan", "activate", "activation", "profile",
        "add esim", "cannot add", "can't add", "cant add", "lpa", "manual entry",
        "setup", "set up", "not registered", "unlock", "locked phone", "carrier lock",
        "roaming", "data roaming",
        "kur", "kurulum", "yükle", "yukle", "tarat", "karekod", "kare kod",
        "aktivasyon", "aktive", "profil", "kilitli", "operatör kilidi", "operator kilidi",
        "dolaşım", "dolasim", "veri dolaşımı", "veri dolasimi",
    ),
    "connection": (
        "no internet", "no data", "not working", "doesn't work", "does not work",
        "won't connect", "wont connect", "can't connect", "cant connect", "no signal",
        "no service", "no network", "sos only", "drops", "disconnect",
        "keeps dropping", "broken", "error code", "gives an error", "error message", "an error", "i get an error",
        "something is wrong", "goes wrong", "problem with", "having trouble",
        "trouble with", "issue with",
        "searching for network", "keeps searching", "says searching",
        "çalışmıyor", "calismiyor", "bağlanmıyor", "baglanmiyor", "internet yok",
        "çekmiyor", "cekmiyor", "sinyal yok", "şebeke yok", "sebeke yok",
        "kopuyor", "bozuk", "şebeke arıyor", "sebeke ariyor",
        # Turkish is agglutinative, so a fixed-phrase list misses "sorunum",
        # "hatalı", "arızası". These stay bare stems: no routine product question
        # contains them, and a missed fault report is a customer sitting unread.
        "hata", "sorun", "arıza", "ariza",
    ),
    "billing": (
        "payment", "paid", "charged", "charge me", "overcharge", "invoice", "receipt",
        "billing", "card declined", "declined", "double charge", "charged twice",
        "paid twice", "billed twice", "crypto", "bitcoin", "usdt",
        "cancel subscription", "cancel my subscription",
        "ödeme", "odeme", "ödedim", "odedim", "fatura", "makbuz", "kart",
        "çekildi", "cekildi", "iki kere ödedim", "iki kere odedim", "çift çekildi",
        "cift cekildi", "aboneliği iptal", "abonelıgı iptal", "abonelik iptal",
    ),
    "refund": (
        "refund", "money back", "chargeback", "reimburse", "cancel my order",
        "iade", "para iadesi", "geri ödeme", "geri odeme", "paramı geri", "parami geri",
    ),
    "urgent": (
        "urgent", "asap", "immediately", "emergency", "stranded", "airport",
        "landing", "boarding", "flight today", "scam", "fraud", "lost money",
        "acil", "hemen", "acele", "havaalanı", "havaalani", "uçuş", "ucus",
        "dolandır", "dolandir", "param gitti", "mağdur", "magdur",
    ),
    "human": (
        "human", "real person", "agent", "live support", "live chat", "operator",
        "talk to someone", "speak to someone", "representative", "manager",
        "gerçek insan", "gercek insan", "canlı destek", "canli destek", "operatör",
        "operator", "temsilci", "yetkili", "birine bağla", "birine bagla",
    ),
    "feature": (
        "feature", "can you add", "please add", "suggestion", "roadmap", "wish",
        "would be nice", "do you support", "is there a way", "esim for",
        "özellik", "ozellik", "öneri", "oneri", "keşke", "keske", "ekleyin",
        "olsa güzel", "olsa guzel", "destekliyor mu",
    ),
    # Money and speed QUESTIONS. Separate flags so the operator still sees what a
    # thread was about, without a "how much is Japan" pulling a person in.
    "pricing": (
        "price", "how much", "cost", "cheap", "coupon", "discount", "promo code",
        "subscription", "renew", "auto-renew", "top up", "top-up",
        "fiyat", "ücret", "ucret", "ne kadar", "kupon", "indirim", "abonelik",
        "yenileme", "yenilenme",
    ),
    "speed": (
        "slow", "speed", "buffering", "throttle",
        "yavaş", "yavas", "hız", "hız ", "hizli", "hızlı",
    ),
}

# Public, stable list of flag names -- the admin filter reads this rather than
# reaching into the keyword table.
INTENT_FLAGS = tuple(sorted(_INTENT_KEYWORDS))

# Flags that pull a human in. Money and connectivity are both time-critical for
# somebody standing in an arrivals hall with no data. Deliberately narrow: the
# assistant exists to answer routine questions about price, subscriptions and
# speed, and escalating those buries the real trouble in the operator inbox.
ESCALATE_FLAGS = {"connection", "billing", "refund", "urgent", "human"}


def detect_intent(text: str) -> set:
    t = (text or "").lower()
    return {flag for flag, words in _INTENT_KEYWORDS.items() if any(w in t for w in words)}


# --- Live account snapshot ---------------------------------------------------
def build_user_context(user) -> dict:
    """Read-only snapshot of the signed-in customer's real data.

    Every lookup is guarded: a schema change in orders or subscriptions must
    degrade the answer quality, never break the chat. Secrets (lpa_code, tokens,
    payment identifiers) are deliberately absent -- the model sees only what the
    customer can already see in their dashboard.
    """
    ctx = {"name": "", "snapshot": "", "has_subscription": False, "is_auth": False}
    if not getattr(user, "is_authenticated", False):
        ctx["snapshot"] = "Not signed in."
        return ctx

    ctx["is_auth"] = True
    try:
        ctx["name"] = (getattr(user, "display_name", "") or "").strip() \
            or (getattr(user, "email", "") or "").split("@")[0]
    except Exception:  # noqa: BLE001
        pass

    lines = []
    try:
        esims = list(user.esims.filter(is_deleted=False).order_by("-created_at")[:5])
        if esims:
            lines.append("Their eSIMs (most recent first):")
            for e in esims:
                bits = [e.plan_title or "eSIM"]
                if e.is_unlimited:
                    bits.append("unlimited data")
                elif e.data_left_gb is not None:
                    bits.append(f"{e.data_left_gb} GB left")
                if e.days_left is not None:
                    bits.append(f"{e.days_left} days left")
                bits.append("active" if e.is_active else ("expired" if e.is_expired else "not started"))
                lines.append(f"- {' | '.join(str(b) for b in bits)}")
        else:
            lines.append("No eSIMs on the account yet.")
    except Exception as e:  # noqa: BLE001
        log.warning("[ASSISTANT] esim snapshot failed: %s", e)

    try:
        orders = list(user.orders.order_by("-created_at")[:5])
        if orders:
            lines.append("Recent orders:")
            for o in orders:
                lines.append(f"- {o.ref}: {o.plan_title or 'plan'} — {o.status}")
    except Exception as e:  # noqa: BLE001
        log.warning("[ASSISTANT] order snapshot failed: %s", e)

    # The subscriptions app may not be installed in every deployment; never let
    # a missing reverse accessor take the chat down.
    try:
        subs = getattr(user, "subscriptions", None)
        if subs is not None:
            active = subs.filter(status="active").count()
            if active:
                ctx["has_subscription"] = True
                lines.append(f"Active auto-renewing subscriptions: {active}.")
            else:
                lines.append("No active subscription.")
    except Exception:  # noqa: BLE001
        pass

    try:
        open_tickets = user.tickets.exclude(status="closed").count()
        if open_tickets:
            lines.append(f"Open support tickets: {open_tickets}.")
    except Exception:  # noqa: BLE001
        pass

    ctx["snapshot"] = "\n".join(lines) or "No account data loaded."
    return ctx


# --- Catalogue knowledge -----------------------------------------------------
# Turkish names for the destinations people actually ask about. Without these a
# Turkish customer asking "italya kac para" gets no price, which is the single
# most common question the assistant receives.
_TR_ALIASES = {
    "italya": "IT", "ispanya": "ES", "fransa": "FR", "almanya": "DE",
    "yunanistan": "GR", "ingiltere": "GB", "birlesik krallik": "GB",
    "amerika": "US", "abd": "US", "japonya": "JP", "tayland": "TH",
    "hollanda": "NL", "belcika": "BE", "avusturya": "AT", "isvicre": "CH",
    "cekya": "CZ", "macaristan": "HU", "polonya": "PL", "portekiz": "PT",
    "hirvatistan": "HR", "sirbistan": "RS", "arnavutluk": "AL",
    "bosna": "BA", "karadag": "ME", "bulgaristan": "BG", "romanya": "RO",
    "rusya": "RU", "ukrayna": "UA", "gurcistan": "GE", "azerbaycan": "AZ",
    "ermenistan": "AM", "kazakistan": "KZ", "ozbekistan": "UZ",
    "misir": "EG", "fas": "MA", "tunus": "TN", "cezayir": "DZ",
    "dubai": "AE", "birlesik arap emirlikleri": "AE", "katar": "QA",
    "suudi arabistan": "SA", "kuveyt": "KW", "umman": "OM", "bahreyn": "BH",
    "urdun": "JO", "israil": "IL", "lubnan": "LB", "kibris": "CY",
    "hindistan": "IN", "cin": "CN", "endonezya": "ID", "bali": "ID",
    "malezya": "MY", "singapur": "SG", "filipinler": "PH", "vietnam": "VN",
    "guney kore": "KR", "kore": "KR", "tayvan": "TW", "hong kong": "HK",
    "avustralya": "AU", "yeni zelanda": "NZ", "kanada": "CA", "meksika": "MX",
    "brezilya": "BR", "arjantin": "AR", "sili": "CL", "kolombiya": "CO",
    "peru": "PE", "guney afrika": "ZA", "kenya": "KE", "nijerya": "NG",
    "turkiye": "TR", "malta": "MT", "irlanda": "IE", "izlanda": "IS",
    "norvec": "NO", "isvec": "SE", "danimarka": "DK", "finlandiya": "FI",
    "maldivler": "MV", "sri lanka": "LK", "nepal": "NP", "pakistan": "PK",
}


_SHORT_ALIASES = {
    "us": "US", "usa": "US", "u.s.": "US", "america": "US", "states": "US",
    "uk": "GB", "britain": "GB", "england": "GB", "scotland": "GB",
    "uae": "AE", "emirates": "AE", "abu dhabi": "AE",
    "nz": "NZ", "aussie": "AU", "oz": "AU",
    "korea": "KR", "holland": "NL", "czech": "CZ", "bali": "ID",
    "phuket": "TH", "ibiza": "ES", "mallorca": "ES", "canaries": "ES",
    "sicily": "IT", "rome": "IT", "milan": "IT", "paris": "FR", "nice": "FR",
    "berlin": "DE", "munich": "DE", "amsterdam": "NL", "lisbon": "PT",
    "barcelona": "ES", "madrid": "ES", "athens": "GR", "crete": "GR",
    "london": "GB", "tokyo": "JP", "osaka": "JP", "bangkok": "TH",
    "istanbul": "TR", "antalya": "TR", "new york": "US", "miami": "US",
    "vegas": "US", "los angeles": "US", "toronto": "CA", "vancouver": "CA",
}


def _fold(text: str) -> str:
    """Lowercase and strip Turkish diacritics so "İtalya" matches "italya"."""
    text = (text or "").lower()
    for a, b in (("ı", "i"), ("İ", "i"), ("ş", "s"), ("ğ", "g"),
                 ("ü", "u"), ("ö", "o"), ("ç", "c"), ("â", "a")):
        text = text.replace(a, b)
    return text


def build_catalogue_context() -> str:
    """A small, true summary of what the shop currently sells.

    Kept deliberately short: the assistant needs to know the shape of the
    catalogue and the entry price, not 1,560 rows. Specific prices come from
    `destination_context`, which only loads the place the customer asked about.
    """
    try:
        from apps.catalog.models import Country, Plan, Region

        live = Plan.objects.live()
        countries = Country.objects.filter(is_active=True)
        cheapest = live.order_by("price_usd").first()
        regions = list(Region.objects.filter(is_active=True).order_by("sort_order")
                       .values_list("name", flat=True))
        unlimited_from = live.filter(is_unlimited=True).order_by("price_usd").first()
        lines = [
            f"Destinations on sale right now: {countries.count()} countries and "
            f"{len(regions)} regional bundles ({', '.join(regions)}).",
            f"Cheapest plan on the whole site: ${cheapest.price} ({cheapest.title})."
            if cheapest else "",
            f"Cheapest unlimited plan: ${unlimited_from.price} ({unlimited_from.title})."
            if unlimited_from else "",
            f"Countries with an unlimited option: {countries.filter(has_unlimited=True).count()}.",
        ]
        return "\n".join(line for line in lines if line)
    except Exception:  # noqa: BLE001
        log.exception("catalogue context failed")
        return "Catalogue summary unavailable; point the customer at the destination pages."


def destination_context(text: str, limit: int = 8) -> str:
    """Real plans for the place the customer just named, or "".

    This is what lets the assistant answer "how much is Italy" with a true price
    instead of refusing. Only the named destination is loaded, so the prompt
    stays small and can never drift out of date.
    """
    if not text:
        return ""
    try:
        from apps.catalog.models import Country, Region

        folded = _fold(text)
        country = None

        # Longest alias first: "new york" must beat "york", "abu dhabi" beat "uae".
        for alias, iso in sorted(
            {**_TR_ALIASES, **_SHORT_ALIASES}.items(), key=lambda kv: -len(kv[0])
        ):
            pattern = r"\b" + re.escape(alias) + r"\b"
            if re.search(pattern, folded):
                country = Country.objects.filter(iso2=iso, is_active=True).first()
                if country:
                    break

        if country is None:
            # Full names, longest first so "United States" wins over "State".
            for c in sorted(Country.objects.filter(is_active=True),
                            key=lambda c: -len(c.name)):
                name = _fold(c.name)
                if len(name) > 3 and re.search(r"\b" + re.escape(name) + r"\b", folded):
                    country = c
                    break

        target, kind = country, "country"
        if target is None:
            for r in Region.objects.filter(is_active=True):
                if _fold(r.name) in folded:
                    target, kind = r, "region"
                    break
        if target is None:
            return ""

        # Take the data plans and the unlimited plans separately. A single
        # ordered slice put every unlimited plan last and the limit cut them off,
        # which made the assistant tell customers a destination had no unlimited
        # option when it did.
        live_plans = target.plans.live()
        data_plans = list(live_plans.filter(is_unlimited=False)
                          .order_by("days", "data_gb")[:limit])
        unlimited = list(live_plans.filter(is_unlimited=True).order_by("days"))
        plans = data_plans + unlimited
        if not plans:
            return ""
        rows = [f"- {p.data_label}, {p.days} days, ${p.price}"
                + (f" (${p.per_gb_usd}/GB)" if p.per_gb_usd else "")
                for p in plans]
        operators = ", ".join(getattr(target, "operator_list", [])[:3])
        header = (f"LIVE PLANS FOR {target.name.upper()} (real prices, quote these freely):")
        extra = []
        if kind == "country" and operators:
            extra.append(f"Networks there: {operators}.")
        if kind == "region":
            extra.append(f"This bundle covers {target.country_count} countries on one profile.")
        extra.append("Unlimited plans for this destination: "
                     + (", ".join(f"{p.days} days ${p.price}" for p in unlimited)
                        if unlimited else "none, this destination has data plans only."))
        extra.append(f"Page: {settings.SITE_URL}{target.get_absolute_url()}")
        return "\n".join([header] + rows + extra)
    except Exception:  # noqa: BLE001
        log.exception("destination context failed")
        return ""


# --- System prompt -----------------------------------------------------------
def build_system_prompt(user_ctx=None, destination: str = "") -> str:
    ctx = user_ctx or {}
    name = (ctx.get("name") or "").strip()
    named = f" ({name})" if name else ""
    if ctx.get("has_subscription"):
        who = (f"The customer{named} pays for an auto-renewing unlimited subscription. "
               "Treat them as a regular: calm, warm, no sales pressure at all.")
    elif ctx.get("is_auth"):
        who = (f"The customer{named} has an account. Answer their question first; only "
               "mention a plan if it genuinely answers what they asked.")
    else:
        who = "Visitor without an account."

    catalogue = build_catalogue_context()
    return f"""You are the eSIMsterr assistant, the in-site helper for eSIMsterr (esimsterr.com), a travel eSIM store. Tagline: "Connect without borders."

LANGUAGE: reply in the SAME language the customer writes in (English to English, Turkish to Turkish, and so on). Keep replies to 2-4 sentences unless they ask for detail. Plain, warm, direct. No exclamation marks, no emoji.

# WHAT WE SELL (never contradict this)
- Prepaid travel eSIM data plans covering 148 countries and 9 regional bundles.
- Plans are DATA ONLY. There are no GSM calls and no SMS on our eSIM. Calls work over WhatsApp, FaceTime, Telegram and similar apps. The customer's own SIM and phone number stay active on the phone, so they keep receiving their bank codes.
- Delivery is instant: the QR code appears on screen and arrives by email the moment payment clears. No passport, no KYC, no shop visit.
- The validity window starts on FIRST CONNECTION at the destination, not at purchase and not at install. Installing the profile at home before flying is fine and is what we recommend.
- An eSIM profile installs on ONE device and usually cannot be moved to another one afterwards.
- Top-ups attach to the SAME eSIM. No reinstall, no second QR code, the ICCID stays the same.
- Payment by card through Stripe, or by crypto through NOWPayments. All prices are in USD.
- Unlimited plans exist for 7, 15 and 30 days, and can also be bought as an auto-renewing subscription.
- The phone must be carrier-unlocked and eSIM-capable.

# THE FIRST THING TO CHECK WHEN DATA DOES NOT WORK
By far the most common fault is Data Roaming being OFF for the eSIM line. Walk the customer through that before anything else:
iPhone: Settings > Mobile Service (Cellular) > pick the eSIM line > turn Data Roaming ON, then set that line for Mobile Data.
Android: Settings > Network and internet > SIMs > pick the eSIM > turn Roaming ON, then set it as the mobile data SIM.
If that is already on: toggle flight mode once, restart the phone, then select the carrier manually in network settings.

# REFUNDS
Only in three cases: the eSIM is still uninstalled and unused and it is within 24 hours of purchase; or we failed to deliver; or it cannot connect and support could not fix it. NEVER promise or approve a refund yourself. Say the team reviews the request, and point them to opening a ticket.

# HARD RULES
- Never invent prices, coverage, countries, dates, speeds or promises. If you do not know, say the team will confirm.
- Never ask for or reveal passwords, card details, or the eSIM activation code / QR content.
- You are read-only. You cannot change, cancel, refund or activate anything on an account.
- If the customer reports a fault, a payment problem, or asks for a human: reassure them, say you are flagging it to the team now, and point them to the support page to open a ticket so it is tracked and answered by email.
- PRICES: every figure you state must be COPIED CHARACTER FOR CHARACTER from the LIVE PLANS block below. Never recall a price from memory, never round one, never average or estimate one, and never carry a price from one destination to another. If the customer asks about something the block does not list, say you will not guess and give them the destination page link. A wrong price is worse than no price: the customer arrives at checkout, sees a different number, and stops trusting the shop.
- Do not claim coverage for a country that is not in the catalogue summary or the live block.

# THE SITE, SO YOU CAN POINT PEOPLE AT THE RIGHT PAGE
- /destinations/ every country. /regions/ multi-country bundles. /unlimited-esim/ the unlimited plans.
- /cheap-esim/ the cheapest plan per destination. /esim-prices/ the full price table.
- /esim/<country>/ one destination and its plans, for example /esim/italy/.
- /how-it-works/ installation in four steps. /esim-compatible-devices/ which phones work.
- /esim-not-working/ the fault checklist. /faq/ common questions. /coupons/ current discount codes.
- /support/ opens a tracked ticket answered by email. /dashboard/ the customer's own eSIMs, QR codes and data left.
Give a path like /esim/italy/ rather than describing where to click.

# WHAT IS ON SALE RIGHT NOW
{catalogue}

# WHO YOU ARE TALKING TO
{who}

# THIS CUSTOMER'S LIVE DATA (read-only, already visible to them in their dashboard)
{ctx.get("snapshot") or "No account data loaded."}

{destination or "NO LIVE PLAN DATA was loaded for this message. You therefore do not know any price for what they asked about. Do not state one. Ask which destination they mean, or send them to /destinations/ or /esim-prices/."}
"""


# --- Anthropic call ----------------------------------------------------------
def _window(history: list) -> list:
    """The tail of the thread, always starting on a customer turn.

    The Messages API rejects a conversation whose first message is not from the
    user, so a fixed slice is not safe: the thread alternates, and once it grows
    past the window the cut lands on an assistant turn every other message. The
    whole call would then fail and the customer would get the fallback line for
    the rest of the conversation, so the window is trimmed forward to the first
    customer message instead.
    """
    window = [m for m in history[-_HISTORY_TURNS:] if m.get("content")]
    while window and window[0].get("role") != "user":
        window.pop(0)
    return window


def _call_anthropic(system: str, history: list, max_tokens: int = 500) -> str:
    api_key = (getattr(settings, "ANTHROPIC_API_KEY", "") or "").strip()
    if not api_key:
        return ""
    messages = [{"role": m["role"], "content": m["content"]} for m in _window(history)]
    if not messages:
        return ""
    try:
        payload = json.dumps({
            "model": _model(),
            "max_tokens": max_tokens,
            # This assistant quotes prices. Sampling is what makes a model
            # reach for a plausible-looking number instead of the one in front
            # of it, so there is nothing to gain here from creativity.
            "temperature": 0,
            "system": system,
            "messages": messages,
        }).encode()
        req = urllib.request.Request(
            _ANTHROPIC_URL, data=payload,
            headers={"content-type": "application/json",
                     "x-api-key": api_key,
                     "anthropic-version": "2023-06-01"},
        )
        with urllib.request.urlopen(req, timeout=_TIMEOUT) as r:  # noqa: S310 - fixed https URL
            result = json.loads(r.read())
        parts = result.get("content") or []
        return "".join(p.get("text", "") for p in parts if p.get("type") == "text").strip()
    except Exception as e:  # noqa: BLE001 - a chat reply is never worth a 500
        log.warning("[ASSISTANT] Anthropic call failed: %s", e)
        return ""


def generate_reply(history, user_ctx=None) -> str:
    """history: [{'role': 'user'|'assistant', 'content': str}, ...].

    The newest customer message decides which destination's real prices are
    loaded into the prompt, so "how much is Italy" is answered with a figure
    rather than deflected to a link.

    Returns "" when the model is unreachable or unconfigured, so the view can
    show a human fallback instead of an error.
    """
    latest = ""
    for message in reversed(history or []):
        if message.get("role") == "user":
            latest = message.get("content") or ""
            break
    return _call_anthropic(
        build_system_prompt(user_ctx, destination=destination_context(latest)),
        history,
    )


# --- Flow-level classification ------------------------------------------------
# Keywords catch what somebody says; they miss what somebody means. "Third time
# this week" carries no keyword and is the most important message in the queue.
# These labels are the ones the keyword table cannot produce, plus the shared
# ones so the model can confirm rather than contradict it.
FLOW_FLAGS = frozenset(INTENT_FLAGS) | {"bug", "purchase", "churn", "praise"}

# What the flow pass is allowed to pull a human in for. Wider than the keyword
# set on purpose: this pass only runs when the keywords found nothing, so these
# are the cases that would otherwise be answered by a robot and left in the
# queue -- somebody about to buy, somebody about to leave, something broken.
FLOW_ESCALATE_FLAGS = ESCALATE_FLAGS | {"bug", "churn", "purchase"}

_FLOW_INSTRUCTION = (
    "You are labelling one customer's conversation with an eSIM shop's support chat. "
    "Judge the whole exchange, not single words. Labels: "
    + ", ".join(sorted(FLOW_FLAGS)) +
    ". Use 'churn' when the customer sounds fed up or about to leave, 'purchase' when "
    "they intend to buy or top up, 'bug' when something on our side is broken, "
    "'feature' when they want something we may not offer, 'praise' when they are happy. "
    'Several may apply. Reply with JSON only: {"intents": ["..."]}'
)


def classify_flow(history) -> set:
    """Intent labels for the conversation as a whole. Empty set on any failure.

    Costs one small call, so the caller only spends it where the cheap keyword
    pass found nothing worth escalating -- the obvious cases are already handled
    for free, and this is only worth paying for on the subtle ones.
    """
    if not history:
        return set()
    transcript = "\n".join(
        f"{m.get('role', '')}: {m.get('content', '')}" for m in history[-8:]
    )
    raw = _call_anthropic(_FLOW_INSTRUCTION,
                          [{"role": "user", "content": transcript}], max_tokens=60)
    if not raw:
        return set()
    # Models wrap JSON in prose and fences often enough that parsing the whole
    # string is the unreliable choice; take the object out of the middle.
    start, end = raw.find("{"), raw.rfind("}")
    if start < 0 or end <= start:
        return set()
    try:
        data = json.loads(raw[start:end + 1])
    except ValueError:
        return set()
    return {str(i) for i in (data.get("intents") or []) if i in FLOW_FLAGS}
