"""GA4 ecommerce events, built server-side.

Why server-side: the numbers that matter here are money, and money is only known
on the server. A `purchase` event assembled in the browser can be replayed by a
page refresh, blocked by an extension, or edited by anyone with devtools, and
every one of those quietly corrupts the revenue report. So views declare the
events they want, this module shapes them into GA4's expected structure, and
base.html emits them once.

The one event that must never fire twice is `purchase`. `Order.analytics_sent`
is the guard: it flips the first time the event is emitted, so a refresh of the
confirmation page reports nothing.

Event names and parameter names are GA4's own. Do not rename them to something
tidier: the standard names are what light up the prebuilt Monetisation reports
and the funnel explorations without any configuration.
"""
from __future__ import annotations

from decimal import Decimal

CURRENCY = "USD"


def _price(value) -> float:
    try:
        return float(Decimal(str(value)).quantize(Decimal("0.01")))
    except Exception:  # noqa: BLE001
        return 0.0


def plan_item(plan, *, index: int = 0, quantity: int = 1) -> dict:
    """One plan as a GA4 item.

    item_category carries country vs region, item_category2 the destination and
    item_category3 the data shape, so the reports can be sliced by "which
    destinations sell" and "do people buy unlimited" without extra setup.
    """
    target = plan.target
    return {
        "item_id": str(plan.provider_plan_id or plan.pk),
        "item_name": plan.title,
        "item_brand": "eSIMsterr",
        "item_category": plan.kind,
        "item_category2": getattr(target, "name", "") or "",
        "item_category3": "unlimited" if plan.is_unlimited else plan.data_label,
        "item_variant": f"{plan.days}d",
        "price": _price(plan.price),
        "quantity": quantity,
        "index": index,
    }


def order_items(order) -> list[dict]:
    """The items on an order.

    Reads the frozen copies on the Order rather than the live Plan: a catalogue
    resync can retire or reprice a plan, and a sale must always report what was
    actually sold at the price actually paid.
    """
    return [{
        "item_id": order.plan_provider_id or "unknown",
        "item_name": order.plan_title,
        "item_brand": "eSIMsterr",
        "item_category": "topup" if order.kind == "topup" else "esim",
        "item_category3": order.plan_data_label or "",
        "item_variant": f"{order.plan_days}d",
        "price": _price(order.subtotal_usd or order.amount_usd),
        "quantity": 1,
        "index": 0,
    }]


def event(name: str, params: dict) -> dict:
    return {"name": name, "params": params}


# --- the events ------------------------------------------------------------
def view_item_list(plans, list_id: str, list_name: str, limit: int = 20) -> dict:
    return event("view_item_list", {
        "item_list_id": list_id,
        "item_list_name": list_name,
        "items": [plan_item(p, index=i) for i, p in enumerate(plans[:limit])],
    })


def view_item(plan) -> dict:
    return event("view_item", {
        "currency": CURRENCY,
        "value": _price(plan.price),
        "items": [plan_item(plan)],
    })


def begin_checkout(order_plan, *, coupon: str = "", value=None) -> dict:
    params = {
        "currency": CURRENCY,
        "value": _price(value if value is not None else order_plan.price),
        "items": [plan_item(order_plan)],
    }
    if coupon:
        params["coupon"] = coupon
    return event("begin_checkout", params)


def add_payment_info(plan, method: str, *, coupon: str = "", value=None) -> dict:
    params = {
        "currency": CURRENCY,
        "value": _price(value if value is not None else plan.price),
        "payment_type": "card" if method == "stripe" else "crypto",
        "items": [plan_item(plan)],
    }
    if coupon:
        params["coupon"] = coupon
    return event("add_payment_info", params)


def purchase(order) -> dict:
    """The money event. Value is what was actually charged, after any coupon."""
    params = {
        "transaction_id": order.ref,
        "currency": CURRENCY,
        "value": _price(order.amount_usd),
        "items": order_items(order),
    }
    if order.discount_usd and order.discount_usd > 0:
        params["coupon"] = order.coupon_code
        # GA4 has no discount field on purchase, so the reduction is reported as
        # the difference between the item price and the transaction value.
    return event("purchase", params)


def refund(order) -> dict:
    return event("refund", {
        "transaction_id": order.ref,
        "currency": CURRENCY,
        "value": _price(order.amount_usd),
        "items": order_items(order),
    })


def sign_up(method: str = "email") -> dict:
    return event("sign_up", {"method": method})


def login(method: str = "email") -> dict:
    return event("login", {"method": method})


def generate_lead(kind: str) -> dict:
    """Support ticket, assistant conversation: intent that is not a sale yet."""
    return event("generate_lead", {"currency": CURRENCY, "value": 0.0, "lead_source": kind})


def subscribe_start(plan, price) -> dict:
    """A subscription checkout. Reported as begin_checkout so it joins the same
    funnel as a one-off, with the recurring nature carried in item_variant."""
    item = plan_item(plan)
    item["item_variant"] = f"{plan.days}d-subscription"
    item["price"] = _price(price)
    return event("begin_checkout", {
        "currency": CURRENCY, "value": _price(price),
        "items": [item], "subscription": True,
    })
