"""Operator alerts: the emails that tell you money moved.

These are written to be read on a phone lock screen in two seconds. The subject
line carries the number, the card leads with revenue, and the line that actually
matters -- what you keep after wholesale and the processor's cut -- is the one
picked out in gold.

Net profit here is deliberately not `Order.margin_usd`. That figure ignores the
payment fee, and on a $7.99 sale Stripe's 2.9% + $0.30 is $0.53, which is a
seventh of the margin. An alert that overstates profit is worse than no alert.
"""
from __future__ import annotations

import logging
from decimal import ROUND_HALF_UP, Decimal

from django.conf import settings
from django.core.mail import EmailMultiAlternatives

logger = logging.getLogger(__name__)

CENT = Decimal("0.01")

# Brand palette, inlined because email clients do not load stylesheets.
NAVY = "#0b2a4a"
BLUE = "#1a8fd1"
CYAN = "#35bdea"
GOLD = "#e0b04a"
MINT = "#34d399"
AMBER = "#fbbf24"
ROSE = "#f87171"


def _d(value) -> Decimal:
    try:
        return Decimal(str(value or 0))
    except Exception:  # noqa: BLE001
        return Decimal("0")


def _money(value) -> str:
    return f"${_d(value).quantize(CENT, rounding=ROUND_HALF_UP)}"


def processor_fee(amount_usd, provider: str) -> Decimal:
    """What the payment processor takes off this sale.

    Rates are settings, not constants: Stripe's cut differs by country and card
    type, and a wrong rate here quietly misreports every profit figure. Defaults
    are Stripe's standard European card pricing and NOWPayments' flat 0.5%.
    """
    amount = _d(amount_usd)
    if provider == "stripe":
        pct = _d(getattr(settings, "STRIPE_FEE_PCT", "2.9")) / 100
        fixed = _d(getattr(settings, "STRIPE_FEE_FIXED_USD", "0.30"))
    elif provider == "nowpayments":
        pct = _d(getattr(settings, "NOWPAYMENTS_FEE_PCT", "0.5")) / 100
        fixed = Decimal("0")
    else:
        return Decimal("0")
    return (amount * pct + fixed).quantize(CENT, rounding=ROUND_HALF_UP)


def sale_economics(order) -> dict:
    """Revenue, cost, fee and what is actually left, for one order."""
    eur_usd = _d(getattr(settings, "EUR_USD_RATE", "1.10"))
    revenue = _d(order.amount_usd)
    cost = _d(order.cost_amount) * (eur_usd if order.cost_currency == "EUR" else Decimal("1"))
    cost = cost.quantize(CENT, rounding=ROUND_HALF_UP)

    payment = order.payments.order_by("-created_at").first()
    provider = payment.provider if payment else "stripe"
    fee = processor_fee(revenue, provider)

    net = (revenue - cost - fee).quantize(CENT, rounding=ROUND_HALF_UP)
    pct = int((net / revenue * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP)) if revenue else 0
    return {"revenue": revenue, "cost": cost, "fee": fee, "net": net,
            "margin_pct": pct, "provider": provider}


def notify_admin(subject: str, text, html: str | None = None) -> None:
    """Send an operator alert. `text` may be a list of lines or a string."""
    recipients = getattr(settings, "ADMIN_NOTIFY_EMAILS", []) or []
    if not recipients:
        logger.info("ADMIN_NOTIFY_EMAILS is empty; dropping alert: %s", subject)
        return
    if isinstance(text, (list, tuple)):
        text = "\n".join(str(line) for line in text)
    try:
        msg = EmailMultiAlternatives(
            f"[{settings.SITE_NAME}] {subject}", text, settings.DEFAULT_FROM_EMAIL, recipients,
        )
        if html:
            msg.attach_alternative(html, "text/html")
        msg.send(fail_silently=True)
    except Exception:  # noqa: BLE001
        logger.exception("Failed to send operator alert")


def admin_card(*, kicker: str, headline: str, subline: str = "", rows=(),
               highlight: tuple[str, str] | None = None, accent: str = BLUE,
               cta_label: str | None = None, cta_url: str | None = None,
               footnote: str = "") -> str:
    """A dark, brand-coloured card built for a phone notification.

    `headline` is the big number, `highlight` is the one figure that should be
    impossible to miss (net profit), `rows` are the supporting detail.
    """
    site = settings.SITE_URL.rstrip("/")
    row_html = "".join(
        '<tr>'
        f'<td style="padding:8px 0;color:#8aa2b8;font-size:13px;white-space:nowrap;">{k}</td>'
        f'<td style="padding:8px 0 8px 18px;color:#e8f2fa;font-size:14px;font-weight:600;'
        f'text-align:right;word-break:break-word;">{v}</td>'
        '</tr>'
        for k, v in rows
    )
    highlight_html = ""
    if highlight:
        label, value = highlight
        highlight_html = f"""
      <table style="width:100%;margin-top:20px;border-collapse:separate;">
        <tr><td style="background:linear-gradient(135deg,#b98b28,{GOLD});border-radius:14px;padding:16px 18px;">
          <div style="font-size:11px;font-weight:800;letter-spacing:.14em;text-transform:uppercase;color:#3b2a06;">{label}</div>
          <div style="margin-top:4px;font-size:30px;font-weight:800;color:#1f1503;line-height:1.1;">{value}</div>
        </td></tr>
      </table>"""
    cta = ""
    if cta_label and cta_url:
        cta = (f'<a href="{cta_url}" style="display:inline-block;margin-top:22px;'
               f'background:{accent};color:#04101f;font-weight:800;padding:13px 26px;'
               f'border-radius:12px;text-decoration:none;font-size:14px;">{cta_label}</a>')
    sub = (f'<div style="margin-top:6px;font-size:14px;color:#9db6cb;">{subline}</div>'
           if subline else "")
    foot = footnote or (
        f"{settings.SITE_NAME} operator alert. You are receiving this because your "
        f"address is in ADMIN_NOTIFY_EMAILS."
    )
    return f"""\
<div style="background:#04101f;padding:26px 14px;font-family:-apple-system,'Segoe UI',Roboto,Arial,sans-serif;">
  <div style="max-width:460px;margin:0 auto;background:#0b1b2e;border:1px solid #16304d;
              border-radius:20px;overflow:hidden;">
    <div style="height:4px;background:linear-gradient(90deg,{BLUE},{CYAN},{GOLD});"></div>
    <div style="padding:22px 26px 12px;">
      <img src="{site}/static/img/logo-wordmark-on-dark.png" alt="{settings.SITE_NAME}"
           width="118" style="display:block;border:0;">
    </div>
    <div style="padding:6px 26px 28px;">
      <div style="font-size:11px;font-weight:800;letter-spacing:.14em;text-transform:uppercase;
                  color:{accent};">{kicker}</div>
      <div style="margin-top:8px;font-size:32px;font-weight:800;color:#ffffff;line-height:1.15;">{headline}</div>
      {sub}
      {highlight_html}
      <table style="width:100%;margin-top:18px;border-collapse:collapse;">{row_html}</table>
      {cta}
    </div>
  </div>
  <div style="max-width:460px;margin:14px auto 0;color:#4e6780;font-size:11px;text-align:center;">
    {foot}
  </div>
</div>"""


# ---------------------------------------------------------------------------
def sale_alert(order, esim=None) -> None:
    """The one you want to feel good about: a completed, delivered sale."""
    e = sale_economics(order)
    admin_url = f"{settings.SITE_URL.rstrip('/')}/admin/orders/order/?q={order.ref}"

    rows = [
        ("Plan", order.plan_title),
        ("Customer", order.email + (" (guest)" if order.is_guest else "")),
        ("Paid via", "Card" if e["provider"] == "stripe" else "Crypto"),
        ("Revenue", _money(e["revenue"])),
        ("Wholesale cost", "-" + _money(e["cost"])),
        ("Processing fee", "-" + _money(e["fee"])),
    ]
    if order.discount_usd and order.discount_usd > 0:
        rows.insert(3, ("Coupon", f"{order.coupon_code} (-{_money(order.discount_usd)})"))
    if esim is not None:
        rows.append(("ICCID", esim.iccid))
    rows.append(("Order", order.ref))

    html = admin_card(
        kicker="New sale",
        headline=_money(e["revenue"]),
        subline=f"{order.plan_title}",
        rows=rows,
        highlight=("Net profit", f'{_money(e["net"])}  ·  {e["margin_pct"]}%'),
        accent=MINT if e["net"] > 0 else ROSE,
        cta_label="Open in admin",
        cta_url=admin_url,
    )
    text = "\n".join([
        f"NEW SALE  {_money(e['revenue'])}",
        f"Net profit {_money(e['net'])} ({e['margin_pct']}%)",
        "",
        f"Plan:      {order.plan_title}",
        f"Customer:  {order.email}{' (guest)' if order.is_guest else ''}",
        f"Paid via:  {'Card' if e['provider'] == 'stripe' else 'Crypto'}",
        f"Revenue:   {_money(e['revenue'])}",
        f"Cost:      -{_money(e['cost'])}",
        f"Fee:       -{_money(e['fee'])}",
        f"Net:       {_money(e['net'])}",
        f"Order:     {order.ref}",
        f"ICCID:     {esim.iccid}" if esim is not None else "",
        "",
        admin_url,
    ])
    notify_admin(f"Sale {_money(e['revenue'])} · net {_money(e['net'])} · {order.plan_title}",
                 text, html)


def failure_alert(order, error: str) -> None:
    """Money taken, nothing delivered. This one has to interrupt you."""
    e = sale_economics(order)
    admin_url = f"{settings.SITE_URL.rstrip('/')}/admin/orders/order/?q={order.ref}"
    html = admin_card(
        kicker="Provisioning failed",
        headline=_money(e["revenue"]) + " taken, not delivered",
        subline="The customer has paid and has no eSIM. The sweeper will retry, "
                "but check the provider balance first.",
        rows=[
            ("Plan", order.plan_title),
            ("Customer", order.email),
            ("Attempts", str(order.fulfillment_attempts)),
            ("Order", order.ref),
            ("Error", (error or "")[:180]),
        ],
        accent=ROSE,
        cta_label="Open in admin",
        cta_url=admin_url,
    )
    notify_admin(
        f"FAILED to deliver {order.ref} · {_money(e['revenue'])} taken",
        [f"Provisioning failed for {order.ref}", f"Customer: {order.email}",
         f"Paid: {_money(e['revenue'])}", f"Attempt: {order.fulfillment_attempts}",
         f"Error: {error}", "", admin_url],
        html,
    )


def underpaid_alert(order, paid_usd) -> None:
    """A crypto invoice came in short: nothing provisioned, on purpose."""
    admin_url = f"{settings.SITE_URL.rstrip('/')}/admin/payments/payment/"
    html = admin_card(
        kicker="Underpaid invoice",
        headline=f"{_money(paid_usd)} of {_money(order.amount_usd)}",
        subline="Nothing was provisioned. Settle it by hand or refund it.",
        rows=[("Plan", order.plan_title), ("Customer", order.email),
              ("Invoiced", _money(order.amount_usd)), ("Received", _money(paid_usd)),
              ("Order", order.ref)],
        accent=AMBER,
        cta_label="Open payments",
        cta_url=admin_url,
    )
    notify_admin(
        f"Underpaid {order.ref} · {_money(paid_usd)} of {_money(order.amount_usd)}",
        [f"Underpaid order {order.ref}", f"Customer: {order.email}",
         f"Invoiced: {_money(order.amount_usd)}", f"Received: {_money(paid_usd)}"],
        html,
    )


def dispute_alert(dispute: dict) -> None:
    """A card dispute / chargeback was opened. This one has to interrupt you: a
    dispute carries a hard evidence deadline and is LOST BY DEFAULT if ignored.

    The Stripe account is shared across products, so we alarm ONLY when the
    disputed PaymentIntent matches one of OUR payments; a dispute on another
    product is skipped (its own webhook alarms it). Never raises — an alert
    failure must not turn the webhook into a 500 (that makes Stripe retry and
    can disable the endpoint, silently breaking settlement)."""
    try:
        from datetime import datetime, timezone as _tz

        from apps.payments.models import Payment

        pi = str(dispute.get("payment_intent") or "")
        payment = (Payment.objects.filter(provider_payment_id=pi)
                   .select_related("user").first()) if pi else None
        if payment is None:
            return  # not one of our charges (shared Stripe account)

        amount = _d(dispute.get("amount", 0)) / 100
        cur = str(dispute.get("currency") or "").upper()
        reason = str(dispute.get("reason") or "")
        status = str(dispute.get("status") or "")
        due_unix = (dispute.get("evidence_details") or {}).get("due_by")
        due = ""
        if due_unix:
            try:
                due = datetime.fromtimestamp(int(due_unix), tz=_tz.utc).strftime("%Y-%m-%d %H:%M UTC")
            except (ValueError, TypeError, OSError):
                due = ""
        email = getattr(payment.user, "email", "") if payment.user_id else ""
        if not email:
            email = getattr(getattr(payment, "order", None), "email", "") or "guest"
        did = str(dispute.get("id") or "")
        stripe_url = f"https://dashboard.stripe.com/disputes/{did}"

        html = admin_card(
            kicker="🚨 Card dispute",
            headline=f"{amount:.2f} {cur} disputed",
            subline="Hard evidence deadline — the dispute is LOST BY DEFAULT if you do not respond in Stripe.",
            rows=[
                ("Customer", email),
                ("Reason", reason or "—"),
                ("Status", status or "—"),
                ("Respond by", due or "—"),
                ("Payment", str(payment.id)),
            ],
            accent=ROSE,
            cta_label="Open dispute in Stripe",
            cta_url=stripe_url,
        )
        notify_admin(
            f"🚨 DISPUTE {amount:.2f} {cur} — {email}",
            ["CARD DISPUTE / CHARGEBACK OPENED",
             f"Customer  : {email}",
             f"Amount    : {amount:.2f} {cur}",
             f"Reason    : {reason or '-'}",
             f"Status    : {status or '-'}",
             f"Respond by: {due or '-'}",
             f"Payment   : {payment.id}",
             "",
             "Submit evidence before the deadline or it is lost by default.",
             stripe_url],
            html,
        )
    except Exception:  # noqa: BLE001
        logger.exception("dispute alert failed")
