"""Operator alert when someone adds credit.

Separate from the sale alert on purpose: money arriving as credit is not revenue
yet -- nothing has been delivered and nothing has cost us anything. Reporting it
as a sale, with a "net profit" line, would overstate the day's takings by the
whole balance.
"""
from __future__ import annotations

from django.conf import settings

from apps.accounts.notifications import (BLUE, GOLD, _money, admin_card, notify_admin,
                                         processor_fee)


def topup_alert(topup) -> None:
    payment = topup.payments.order_by("-created_at").first()
    provider = payment.provider if payment else "stripe"
    fee = processor_fee(topup.amount_usd, provider)
    net_cash = topup.amount_usd - fee

    rows = [
        ("Customer", topup.user.email),
        ("Paid via", "Card" if provider == "stripe" else "Crypto"),
        ("Invoiced", _money(topup.amount_usd)),
        ("Provider reported", _money(topup.received_usd)
            if topup.received_usd is not None else "not reported"),
        ("Processing fee", "-" + _money(fee)),
        ("Bonus given", "+" + _money(topup.bonus_usd)),
        ("Credited", _money(topup.credited_usd or topup.total_usd)),
        ("From", topup.source),
        ("Reference", topup.ref),
    ]
    html = admin_card(
        kicker="Balance added",
        headline=_money(topup.amount_usd),
        subline=f"{topup.user.email} now holds "
                f"{_money(topup.user.wallet.balance_usd)} in credit.",
        rows=rows,
        highlight=("Cash in, after fees", _money(net_cash)),
        accent=BLUE,
        cta_label="Open wallet in admin",
        cta_url=f"{settings.SITE_URL.rstrip('/')}/admin/wallet/balancetopup/",
        footnote="This is deferred revenue: it becomes a sale when the customer "
                 "spends it, and that is when profit is reported.",
    )
    notify_admin(
        f"Balance +{_money(topup.amount_usd)} · {topup.user.email}",
        [f"BALANCE ADDED {_money(topup.amount_usd)}",
         f"Customer: {topup.user.email}",
         f"Bonus:    +{_money(topup.bonus_usd)}",
         f"Credited: {_money(topup.credited_usd or topup.total_usd)}",
         f"Fee:      -{_money(fee)}",
         f"Cash in:  {_money(net_cash)}",
         f"Source:   {topup.source}",
         f"Ref:      {topup.ref}"],
        html,
    )
