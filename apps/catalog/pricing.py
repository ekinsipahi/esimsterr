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


def compare_at_usd(retail: Decimal, *, is_unlimited: bool = False) -> Decimal:
    """A conservative 'what others charge' figure for the strike-through: the big
    apps are typically 2–3x our retail for the same allowance. We show 1.9x for
    data plans and 1.6x for unlimited so the claim stays defensible."""
    factor = Decimal("1.6") if is_unlimited else Decimal("1.9")
    return charm((retail * factor).quantize(CENT, rounding=ROUND_HALF_UP))
