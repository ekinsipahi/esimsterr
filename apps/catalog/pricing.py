"""Retail pricing strategy.

Positioning: undercut the big eSIM apps (Airalo/Holafly/Cellesim/esim.io) while
keeping a healthy margin. Wholesale (EUR) → USD → markup → floor → charm rounding.
Every knob is an env var; a per-plan `price_override_usd` in admin always wins.
"""
from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal

from django.conf import settings

CENT = Decimal("0.01")


def _d(v) -> Decimal:
    return Decimal(str(v))


def cost_to_usd(cost_amount, currency: str) -> Decimal:
    amt = _d(cost_amount)
    if (currency or "EUR").upper() == "EUR":
        amt = amt * _d(settings.EUR_USD_RATE)
    return amt.quantize(CENT, rounding=ROUND_HALF_UP)


def charm(price: Decimal) -> Decimal:
    """Round UP to the next .49 / .99 ending (never below the computed price)."""
    whole = int(price)
    frac = price - whole
    if frac <= Decimal("0.49"):
        return _d(whole) + Decimal("0.49")
    if frac <= Decimal("0.99"):
        return _d(whole) + Decimal("0.99")
    return _d(whole + 1) + Decimal("0.49")


def retail_usd(cost_amount, currency: str = "EUR", *, is_unlimited: bool = False) -> Decimal:
    cost = cost_to_usd(cost_amount, currency)
    markup = _d(settings.PRICING_MARKUP)
    price = max(cost * markup, cost + _d(settings.PRICING_MIN_MARGIN_USD))
    price = max(price, _d(settings.PRICING_MIN_PRICE_USD))
    return charm(price.quantize(CENT, rounding=ROUND_HALF_UP))


def compare_at_usd(cost_amount, currency: str = "EUR", **_ignored) -> Decimal:
    """The list price: what the same wholesale data costs at a normal retail margin.

    Anchored to COST, not to our own price, so it tracks the market rather than
    drifting with our discounting. The big eSIM apps run roughly a 4x margin on
    the same wholesale supply — a spot check against Cellesim's Italy 10 GB plan
    ($16.65) lands within a dollar of this formula — so `PRICING_COMPARE_MULTIPLIER`
    defaults to 4.0 and we sell at `PRICING_MARKUP` (1.65). The gap between the
    two is the percentage the customer sees.

    Note for whoever tunes this: the strike-through is presented as the going
    market rate, not as a former eSIMsterr price. Keep the label honest in the
    templates, and keep the multiplier defensible — if the market moves, move it.
    """
    cost = cost_to_usd(cost_amount, currency)
    factor = _d(getattr(settings, "PRICING_COMPARE_MULTIPLIER", "4.0"))
    listed = max(cost * factor, _d(settings.PRICING_MIN_PRICE_USD) + _d("1.50"))
    return charm(listed.quantize(CENT, rounding=ROUND_HALF_UP))


def discount_pct(price: Decimal, compare_at: Decimal) -> int:
    """Whole-number percentage off the list price, floored at 0."""
    if not compare_at or compare_at <= price:
        return 0
    return int(((compare_at - price) / compare_at * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
