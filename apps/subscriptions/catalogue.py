"""Which plans we sell as a subscription, and what they cost.

WHY THIS IS A SHORT LIST. Every unlimited plan used to be subscribable, which
came to 257 of them, 245 of those for a single country. Nobody wants "Turkey,
unlimited, renewing every week": people travel for a fortnight, come home, and
then see a charge for a country they have left. That charge is a refund request
at best and a chargeback at worst, and neither is worth the revenue.

A subscription makes sense for someone who is continuously somewhere, so the
list is the unlimited regional plans and nothing else. There are four of them
because there are four: those are the only regions the provider sells an
unlimited plan for.

WHY THE PRICES ARE WRITTEN DOWN. Everywhere else in this codebase a price is
derived: wholesale times a markup, charmed to a .99. That produced a regional
ladder running $16.49, $20.49, $25.49, $61.99, $128.99 -- each one defensible on
its own and the set of them meaningless to a customer. A subscription is a price
somebody agrees to keep paying, so it is chosen rather than computed.

WHY THERE IS NO WORLDWIDE PLAN HERE. There is no Global unlimited to sell. The
provider ships twelve worldwide plans and every one of them is a gigabyte
allowance; nothing unlimited anywhere in the catalogue runs longer than 30 days
either. So a worldwide or an annual unlimited subscription is not a thing we
have chosen against, it is a thing that cannot be bought wholesale. The nearest
possible offer is a worldwide gigabyte bundle billed yearly, which is a
different product and is deliberately not on this menu.

"""
from __future__ import annotations

import logging
from decimal import Decimal

from django.conf import settings

from apps.catalog.pricing import cost_to_usd

log = logging.getLogger(__name__)

# (region slug, days, data_gb or None for unlimited) -> price per cycle in USD.
#
# Margins against wholesale at the time of writing, which is the number that
# matters because it is paid again on every renewal:
#
#   Europe          21.46  ->  29.99   1.40x
#   Balkans         27.34  ->  39.99   1.46x
#   Southeast Asia  33.64  ->  49.99   1.49x
#   Latin America   78.10  -> 114.99   1.47x
FIXED_PRICES: dict[tuple[str, int, int | None], str] = {
    # Monthly, regional, unlimited. These four are the whole menu: they are the
    # only regions the provider sells an unlimited plan for.
    ("europe", 30, None): "29.99",
    ("balkans", 30, None): "39.99",
    ("southeast-asia", 30, None): "49.99",
    ("latin-america", 30, None): "114.99",
}

# Worldwide gigabyte bundles billed yearly. Kept here rather than deleted
# because the wholesale is unusually good -- $32.56 for 20 GB across a year
# against $22.00 for one month of it -- so this is a line worth reaching for if
# a worldwide subscription is ever wanted. Merge it into FIXED_PRICES to switch
# it on; it is off because the menu is unlimited plans only.
ANNUAL_WORLDWIDE: dict[tuple[str, int, int | None], str] = {
    ("global", 365, 20): "59.99",
    ("global", 365, 40): "114.99",
    ("global", 365, 80): "149.99",
}


def _key(plan) -> tuple[str, int, int | None] | None:
    region = getattr(plan, "region", None)
    if region is None or not region.slug:
        return None
    gigabytes = None
    if not plan.is_unlimited:
        if plan.data_gb is None:
            return None
        gigabytes = int(Decimal(str(plan.data_gb)))
    return (region.slug, int(plan.days or 0), gigabytes)


def is_subscribable(plan) -> bool:
    """Whether this plan is one of the few we offer on a recurring basis."""
    key = _key(plan)
    return key is not None and key in FIXED_PRICES


def subscribable(queryset=None):
    """The plans on the subscription menu, cheapest first.

    Built by filtering rather than by a flag on the model: the provider's
    catalogue is re-synced nightly and a flag would have to be reapplied every
    time, which is a job that eventually gets skipped.

    Where the provider ships more than one plan answering to the same key, the
    cheaper wholesale wins: the price the customer pays is fixed and the cost is
    not, so the margin is ours to take rather than theirs to choose.
    """
    from apps.catalog.models import Plan

    plans = (queryset if queryset is not None else Plan.objects.live())
    plans = plans.select_related("region", "country").order_by("cost_amount")

    chosen: dict[tuple, object] = {}
    for plan in plans:
        key = _key(plan)
        if key in FIXED_PRICES and key not in chosen:
            chosen[key] = plan
    return sorted(chosen.values(), key=lambda p: (p.days, fixed_price(p) or 0))


def fixed_price(plan) -> Decimal | None:
    """The agreed price for this plan, or None if it is not on the menu.

    Returns None as well when wholesale has risen past what we agreed to charge.
    A fixed price is a promise to the customer, not to the provider, and the one
    thing worse than repricing is a renewal that loses money every month
    unattended -- so the caller falls back to the computed price and the
    operator gets told.
    """
    key = _key(plan)
    if key is None or key not in FIXED_PRICES:
        return None

    price = Decimal(FIXED_PRICES[key])
    floor = (cost_to_usd(plan.cost_amount, plan.cost_currency)
             + Decimal(str(settings.PRICING_MIN_MARGIN_USD)))
    if price < floor:
        log.warning(
            "Subscription price for %s is $%s but wholesale has risen to $%s; "
            "falling back to the computed price. Reprice it in "
            "apps/subscriptions/catalogue.py.",
            plan.title, price, floor,
        )
        return None
    return price.quantize(Decimal("0.01"))
