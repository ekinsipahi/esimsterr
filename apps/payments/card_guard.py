"""Card testing defence, in front of Stripe rather than behind it.

Somebody with a list of stolen card numbers needs a cheap endpoint that will
authorise a small amount, and a top-up form is exactly that. They do not want
the balance; they want to know which numbers still work, and they find out by
failing hundreds of times.

The throttles already on these endpoints do not stop it, because a throttle
counts *requests*. A customer adding $25 and a bot trying two hundred stolen
cards both make requests; only one of them is declined every single time. So
this counts failures instead, and it counts how many different cards one
identity has tried -- the part no real buyer looks like, because a person has
one card, maybe two.

**The cooldown is a ladder, not a wall.** A first decline costs nothing: the
commonest reason for one is a typo or a card the bank wants to check. Each
further decline costs more, so by the fifth the attempt is an hour away. That
shape is close to free for a customer having a bad minute and ruinous for a
script, where the whole method depends on volume.

**Three identities, not one.** An attacker who registers a new account keeps the
same address; one who changes address keeps the same email. Counting against
account, address and email together means each evasion still walks into one of
the other two.

**The address limits are deliberately loose.** This is a travel product: an
airport, a hotel and a cruise ship each put every customer behind one NAT
address, so a strict per-IP rule locks out exactly the people the app is for.
The per-account rungs are tight, the per-address ones are generous, and the rule
that catches a distributed attempt is the card count rather than the request
count.

**Why in front of Stripe rather than left to Radar.** Radar decides after the
attempt has been made, and an attempt that reaches Stripe is one we are billed
for and one that lands in the logs. Radar stays on with its own rules; this is
the layer that keeps the obvious cases from reaching it.

None of this replaces settling on the webhook. Credit is granted when Stripe
says the money arrived and never on the client's word -- see
apps.payments.services.
"""
from __future__ import annotations

import logging
import time

from django.conf import settings
from django.core.cache import cache

log = logging.getLogger(__name__)

PREFIX = "cardguard"

# Seconds to wait before the next attempt, by how many declines are already in
# the window. The first costs nothing; the fifth costs an hour.
DEFAULT_LADDER = (0, 30, 120, 600, 3600)

# Throwaway inbox providers. Short on purpose: the full public lists run to tens
# of thousands of domains, go stale within weeks, and the long tail is where the
# false positives live. These are the ones that actually turn up, and
# CARD_GUARD_DISPOSABLE_DOMAINS extends the list without a deploy.
#
# A disposable address is not fraud by itself -- some people guard their inbox
# and have every right to. It is a signal, and it is used as one: it costs an
# attempt nothing until something else about the attempt is also wrong.
DISPOSABLE_DOMAINS = frozenset({
    "0-mail.com", "10minutemail.com", "20minutemail.com", "33mail.com",
    "anonbox.net", "byom.de", "dispostable.com", "dropmail.me", "emailondeck.com",
    "fakeinbox.com", "getairmail.com", "getnada.com", "guerrillamail.com",
    "guerrillamail.info", "inboxbear.com", "inboxkitten.com", "mail-temp.com",
    "mail7.io", "mailcatch.com", "maildrop.cc", "mailinator.com", "mailnesia.com",
    "mailsac.com", "mintemail.com", "mohmal.com", "moakt.com", "mytemp.email",
    "nowmymail.com", "sharklasers.com", "spam4.me", "temp-mail.io",
    "temp-mail.org", "tempail.com", "tempinbox.com", "tempmail.dev",
    "tempmail.ninja", "tempmailo.com", "tempr.email", "throwawaymail.com",
    "trashmail.com", "trashmail.de", "trbvm.com", "yopmail.com", "yopmail.fr",
})


class CardTestingBlocked(Exception):
    """Refused before Stripe was called.

    `reason` is for the log and for support. The customer-facing text says only
    that it did not work and when to try again: naming the rule that tripped
    tells an attacker exactly what to vary.
    """

    def __init__(self, reason: str, retry_after: int):
        super().__init__(reason)
        self.reason = reason
        self.retry_after = max(int(retry_after), 1)

    @property
    def message(self) -> str:
        wait = self.retry_after
        when = (f"{wait} seconds" if wait < 90
                else f"{round(wait / 60)} minutes" if wait < 3600
                else "an hour")
        return (f"We could not take that payment. Please wait {when} before "
                f"trying again, or contact support if this keeps happening.")


def _conf(name: str, default):
    return getattr(settings, name, default)


def _enabled() -> bool:
    return bool(_conf("CARD_GUARD_ENABLED", True))


def _window() -> int:
    return int(_conf("CARD_GUARD_WINDOW_SECONDS", 3600))


def _ladder() -> tuple[int, ...]:
    raw = _conf("CARD_GUARD_COOLDOWN_LADDER", DEFAULT_LADDER)
    if isinstance(raw, str):
        try:
            raw = tuple(int(x) for x in raw.split(",") if x.strip())
        except ValueError:
            raw = DEFAULT_LADDER
    return tuple(raw) or DEFAULT_LADDER


# ---- cache helpers -----------------------------------------------------------
# Timestamps rather than a counter, so the window slides instead of resetting on
# the hour. A counter lets an attacker wait for the tick and start again.
def _recent(key: str, window: int) -> list[float]:
    now = time.time()
    return [t for t in (cache.get(key) or []) if now - t < window]


def _push(key: str, window: int) -> list[float]:
    hits = _recent(key, window)
    hits.append(time.time())
    cache.set(key, hits, window)
    return hits


def _cards(key: str, window: int) -> dict:
    now = time.time()
    return {f: t for f, t in (cache.get(key) or {}).items() if now - t < window}


def _add_card(key: str, fingerprint: str, window: int) -> int:
    seen = _cards(key, window)
    seen[fingerprint] = time.time()
    cache.set(key, seen, window)
    return len(seen)


def identities(user, ip: str = "", email: str = "") -> list[tuple[str, str]]:
    """What this attempt is counted against, most specific first.

    Account, address and email. An attacker shedding one of the three still
    carries the other two.
    """
    out: list[tuple[str, str]] = []
    uid = getattr(user, "pk", None)
    if uid:
        out.append(("user", str(uid)))
    address = (ip or "").strip()
    if address and address != "unknown":
        out.append(("ip", address))
    mail = (email or getattr(user, "email", "") or "").strip().lower()
    if mail:
        out.append(("email", mail))
    return out


def _cooldown_for(kind: str, failures: int) -> int:
    # `failures` counts declines already recorded, so the first one indexes the
    # first rung -- which is zero. Indexing by the count itself would charge a
    # customer 30 seconds for one mistyped digit, which is the behaviour this
    # ladder exists to avoid.
    ladder = _ladder()
    step = ladder[min(failures - 1, len(ladder) - 1)] if failures else 0
    # An address is shared by strangers, so its ladder is softened rather than
    # skipped: a hotel lobby should slow down, not stop.
    if kind == "ip":
        step = int(step * float(_conf("CARD_GUARD_IP_COOLDOWN_FACTOR", 0.25)))
    return int(step)


# ---- what the rest of the code calls -----------------------------------------
def _extra_rungs(user, email: str) -> int:
    """How far up the ladder an attempt starts before it has failed anything.

    Nothing here is proof of fraud; each is a thing that is ordinary once and
    odd in combination. Starting a rung or two up costs an honest customer a
    short wait on their *second* mistake and costs a script the volume it needs.
    """
    rungs = 0
    minutes = int(_conf("CARD_GUARD_FRESH_ACCOUNT_MINUTES", 15))
    joined = getattr(user, "date_joined", None)
    if joined and minutes:
        try:
            from django.utils import timezone
            if (timezone.now() - joined).total_seconds() < minutes * 60:
                rungs += 1
        except Exception:  # noqa: BLE001 — a clock problem must not block a sale
            pass
    if email_is_disposable(email or getattr(user, "email", "")):
        rungs += 1
    return rungs


def check(user, ip: str = "", email: str = "") -> None:
    """Raise if this account, address or email is still cooling down."""
    if not _enabled():
        return
    window, now = _window(), time.time()

    # A throwaway inbox, on its own, before anything has gone wrong.
    #
    # Refused by default because that is the policy asked for, but it is the one
    # rule here that can turn away a real customer: some people guard their inbox
    # and are entitled to. CARD_GUARD_BLOCK_DISPOSABLE_EMAIL=False softens it to
    # a rung on the ladder instead, which is the setting to reach for if support
    # starts hearing about it.
    address_used = (email or getattr(user, "email", "") or "")
    if _conf("CARD_GUARD_BLOCK_DISPOSABLE_EMAIL", True) and email_is_disposable(address_used):
        raise CardTestingBlocked(
            f"disposable email domain: {address_used.rpartition('@')[2]}",
            int(_conf("CARD_GUARD_BLOCK_SECONDS", 3600)),
        )

    head_start = _extra_rungs(user, email)

    for kind, ident in identities(user, ip, email):
        key = f"{kind}:{ident}"

        hard = cache.get(f"{PREFIX}:blocked:{key}")
        if hard:
            raise CardTestingBlocked(f"{kind} {ident} blocked: {hard}",
                                     int(_conf("CARD_GUARD_BLOCK_SECONDS", 3600)))

        fails = _recent(f"{PREFIX}:fail:{key}", window)
        if not fails:
            continue
        wait = _cooldown_for(kind, len(fails) + head_start)
        elapsed = now - max(fails)
        if wait and elapsed < wait:
            raise CardTestingBlocked(
                f"{kind} {ident} has {len(fails)} declines; {int(wait - elapsed)}s of "
                f"cooldown left",
                wait - elapsed,
            )

    if ip and ip != "unknown":
        attempts = len(_recent(f"{PREFIX}:try:ip:{ip}", window))
        if attempts >= int(_conf("CARD_GUARD_IP_ATTEMPTS", 40)):
            raise CardTestingBlocked(f"ip {ip} made {attempts} attempts in {window}s", window)


def record_attempt(user, ip: str = "", email: str = "") -> None:
    """Called when a payment sheet or checkout session is about to be created."""
    if not _enabled():
        return
    if ip and ip != "unknown":
        _push(f"{PREFIX}:try:ip:{ip}", _window())


def record_failure(user, ip: str = "", email: str = "",
                   fingerprint: str = "", decline_code: str = "") -> None:
    """Called from the Stripe webhook when an attempt is declined.

    The failure count drives the cooldown ladder. The distinct-card count is a
    separate, harder rule: one identity trying several different cards in an
    hour is not a customer having trouble, it is a list being worked through,
    and that earns a flat block rather than a rung.
    """
    if not _enabled():
        return
    window = _window()

    # The card itself, independently of who presented it. Four declines on one
    # number is that number being tested, whichever account or address it
    # arrives from next.
    if fingerprint:
        tries = _push(f"{PREFIX}:fail:card:{fingerprint}", window)
        index = [f for f in (cache.get(f"{PREFIX}:cardindex") or []) if f != fingerprint]
        cache.set(f"{PREFIX}:cardindex", (index + [fingerprint])[-500:], window)
        limit = int(_conf("CARD_GUARD_CARD_FAILURES", 4))
        if len(tries) >= limit:
            cache.set(f"{PREFIX}:blocked:card:{fingerprint}",
                      f"{len(tries)} declines in {window}s",
                      int(_conf("CARD_GUARD_BLOCK_SECONDS", 3600)))
            log.warning("Card guard blocked card %s…: %d declines in %ds",
                        fingerprint[:8], len(tries), window)

    for kind, ident in identities(user, ip, email):
        key = f"{kind}:{ident}"
        fails = _push(f"{PREFIX}:fail:{key}", window)
        log.info("Card guard: %s %s now has %d declines in %ds (code %r)",
                 kind, ident, len(fails), window, decline_code or "none")

        if fingerprint:
            distinct = _add_card(f"{PREFIX}:cards:{key}", fingerprint, window)
            limit = int(_conf(f"CARD_GUARD_{kind.upper()}_CARDS",
                              3 if kind in ("user", "email") else 8))
            if distinct >= limit:
                cache.set(f"{PREFIX}:blocked:{key}",
                          f"{distinct} different cards in {window}s",
                          int(_conf("CARD_GUARD_BLOCK_SECONDS", 3600)))
                log.warning("Card guard blocked %s %s: %d distinct cards in %ds",
                            kind, ident, distinct, window)


def record_success(user, ip: str = "", email: str = "") -> None:
    """A real payment landed, so let go of the failures that preceded it.

    Somebody whose first card is declined and whose second one works is a
    customer, not an attack, and must not spend the rest of the window one
    mistake away from an hour's wait.
    """
    if not _enabled():
        return
    for kind, ident in identities(user, ip, email):
        key = f"{kind}:{ident}"
        cache.delete(f"{PREFIX}:fail:{key}")
        cache.delete(f"{PREFIX}:cards:{key}")
        cache.delete(f"{PREFIX}:blocked:{key}")


def disposable_domains() -> frozenset[str]:
    extra = _conf("CARD_GUARD_DISPOSABLE_DOMAINS", "")
    if isinstance(extra, str):
        extra = [d.strip().lower() for d in extra.split(",") if d.strip()]
    return DISPOSABLE_DOMAINS | frozenset(extra or ())


def email_is_disposable(email: str) -> bool:
    domain = (email or "").strip().lower().rpartition("@")[2]
    if not domain:
        return False
    # Sub-addressed throwaways (foo.mailinator.com) resolve to the parent.
    parts = domain.split(".")
    return any(".".join(parts[i:]) in disposable_domains() for i in range(len(parts) - 1))


def check_card(fingerprint: str) -> None:
    """Refuse a card that has already been declined repeatedly.

    Only reachable where the payment method is known before the charge, which
    means a saved card. A card typed into the sheet is not known until Stripe
    reports the failure, so for those this rule acts through the per-identity
    card count instead -- and through Stripe Radar, which can hold the same
    fingerprints in its blocklist.

    The fingerprint is Stripe's. The card number is never stored here, and a
    fingerprint cannot be turned back into one.
    """
    if not (_enabled() and fingerprint):
        return
    reason = cache.get(f"{PREFIX}:blocked:card:{fingerprint}")
    if reason:
        raise CardTestingBlocked(f"card {fingerprint[:8]}… blocked: {reason}",
                                 int(_conf("CARD_GUARD_BLOCK_SECONDS", 3600)))


def blocked_cards() -> list[str]:
    """Fingerprints currently refused, for pushing into Stripe Radar's blocklist.

    Radar enforces at Stripe's edge, which stops the attempt before it is billed
    to us at all. This list is what to paste there; the local block is the part
    that works in the minutes before anyone does.
    """
    return [f for f in (cache.get(f"{PREFIX}:cardindex") or []) 
            if cache.get(f"{PREFIX}:blocked:card:{f}")]


def fingerprint_of(intent: dict) -> str:
    """Stripe's fingerprint for the card that was declined, if it is there.

    A fingerprint is stable for the same card across customers, which is what
    makes it useful here: it notices one list being tried from several accounts.
    It is not the card number and cannot be turned back into one.
    """
    err = (intent or {}).get("last_payment_error") or {}
    card = (err.get("payment_method") or {}).get("card") or {}
    return str(card.get("fingerprint") or "")


def decline_code_of(intent: dict) -> str:
    err = (intent or {}).get("last_payment_error") or {}
    return str(err.get("decline_code") or err.get("code") or "")
