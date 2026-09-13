"""Shared presentation tags: inline SVG icons, real flag images, money helpers.

Why a tag and not emoji: emoji flags do not render at all on Windows (the user
sees the two-letter country code instead, e.g. "CD" for Congo), and emoji
pictographs render differently on every platform. Everything visual here is an
SVG we ship, so it looks identical everywhere and inherits `currentColor`.
"""
from __future__ import annotations

import json
import os
from decimal import Decimal

from django import template
from django.conf import settings
from django.templatetags.static import static
from django.utils.html import format_html
from django.utils.safestring import mark_safe

register = template.Library()

# --- Flags -------------------------------------------------------------------
# Vendored from flag-icons (MIT) into static/vendor/flags/<iso2>.svg.
FLAG_DIR = "vendor/flags"
# Codes the provider uses that the ISO set does not carry 1:1.
FLAG_ALIASES = {
    "AN": "cw",   # Netherlands Antilles (dissolved) -> Curaçao
    "UK": "gb",
    "XK": "xk",
}


def _flag_file(iso2: str) -> str | None:
    code = FLAG_ALIASES.get((iso2 or "").upper(), (iso2 or "").lower())
    if not code:
        return None
    path = os.path.join(settings.BASE_DIR, "static", FLAG_DIR, f"{code}.svg")
    return f"{FLAG_DIR}/{code}.svg" if os.path.exists(path) else None


def flag_url(iso2) -> str:
    """Static URL of a country's flag, or "" when we ship no flag for that code.
    Used by JSON endpoints, which cannot render a template tag."""
    rel = _flag_file(iso2)
    return static(rel) if rel else ""


@register.simple_tag
def flag(iso2, size=24, cls=""):
    """<img> of a real SVG flag. Falls back to a neutral globe chip when the
    provider sends a code we have no flag for, so a page never 404s an image."""
    rel = _flag_file(iso2)
    classes = f"flag {cls}".strip()
    if rel is None:
        return format_html(
            '<span class="{} flag-unknown" style="width:{}px;height:{}px" aria-hidden="true">{}</span>',
            classes, size, round(size * 0.75), (iso2 or "?")[:2].upper(),
        )
    return format_html(
        '<img src="{}" class="{}" width="{}" height="{}" alt="" loading="lazy" decoding="async">',
        static(rel), classes, size, round(size * 0.75),
    )


@register.filter
def has_flag(iso2):
    return _flag_file(iso2) is not None


# --- Icons -------------------------------------------------------------------
# Lucide-style 24x24 stroke paths. Add here, never inline an emoji in a template.
_P = {
    # navigation / product
    "globe": '<circle cx="12" cy="12" r="10"/><path d="M2 12h20M12 2a15 15 0 0 1 0 20 15 15 0 0 1 0-20"/>',
    "map-pin": '<path d="M20 10c0 6-8 12-8 12s-8-6-8-12a8 8 0 0 1 16 0z"/><circle cx="12" cy="10" r="3"/>',
    "layers": '<path d="M3 7 9 4l6 3 6-3v13l-6 3-6-3-6 3z"/><path d="M9 4v13M15 7v13"/>',
    "infinity": '<path d="M18.2 14.8a4 4 0 1 1 0-5.6L12 12l-6.2 2.8a4 4 0 1 1 0-5.6L12 12z"/>',
    "sim": '<path d="M5 4.5A1.5 1.5 0 0 1 6.5 3h6.7L19 8.8V19.5A1.5 1.5 0 0 1 17.5 21h-11A1.5 1.5 0 0 1 5 19.5z"/><rect x="8.5" y="11" width="7" height="6" rx="1.2"/><path d="M11 11v6M8.5 14h7"/>',
    "qr": '<rect x="3" y="3" width="7" height="7" rx="1"/><rect x="14" y="3" width="7" height="7" rx="1"/><rect x="3" y="14" width="7" height="7" rx="1"/><path d="M14 14h3v3h-3zM20 14h1M14 20h3M20 17v4"/>',
    "smartphone": '<rect x="5" y="2" width="14" height="20" rx="2.5"/><path d="M12 18h.01"/>',
    "signal": '<path d="M2 20h.01M7 20v-4M12 20v-8M17 20v-12M22 20V4"/>',
    "wifi": '<path d="M5 12.5a10 10 0 0 1 14 0M8.5 16a5 5 0 0 1 7 0M12 19.5h.01M1.5 9a15 15 0 0 1 21 0"/>',
    # trust / state
    "check": '<path d="M20 6 9 17l-5-5"/>',
    "check-circle": '<circle cx="12" cy="12" r="10"/><path d="m8 12 3 3 5-6"/>',
    "shield": '<path d="M12 2 4 6v6c0 5 3.4 8.7 8 10 4.6-1.3 8-5 8-10V6z"/><path d="m9 12 2 2 4-4"/>',
    "lock": '<rect x="3" y="11" width="18" height="11" rx="2"/><path d="M7 11V7a5 5 0 0 1 10 0v4"/>',
    "zap": '<path d="M13 2 3 14h9l-1 8 10-12h-9l1-8z"/>',
    "clock": '<circle cx="12" cy="12" r="10"/><path d="M12 6v6l4 2"/>',
    "calendar": '<rect x="3" y="5" width="18" height="16" rx="2"/><path d="M3 10h18M8 3v4M16 3v4"/>',
    "alert": '<path d="M12 9v4M12 17h.01M10.3 3.9 1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0z"/>',
    "info": '<circle cx="12" cy="12" r="10"/><path d="M12 16v-4M12 8h.01"/>',
    "x": '<path d="M18 6 6 18M6 6l12 12"/>',
    "refresh": '<path d="M21 12a9 9 0 1 1-6.2-8.6"/><path d="M21 3v6h-6"/>',
    # money / commerce
    "tag": '<path d="M20.6 13.4 12 22l-9-9V3h10l7.6 7.6a2 2 0 0 1 0 2.8z"/><circle cx="7.5" cy="7.5" r="1.4"/>',
    "credit-card": '<rect x="2" y="5" width="20" height="14" rx="2.5"/><path d="M2 10h20"/>',
    "bitcoin": '<circle cx="12" cy="12" r="10"/><path d="M9.5 7.5h4a2.3 2.3 0 0 1 0 4.6h-4zM9.5 12.1h4.4a2.3 2.3 0 0 1 0 4.6H9.5zM9.5 7.5v9.2M11.5 5.5v2M14 5.5v2M11.5 16.7v2M14 16.7v2"/>',
    "percent": '<path d="M19 5 5 19"/><circle cx="6.5" cy="6.5" r="2.5"/><circle cx="17.5" cy="17.5" r="2.5"/>',
    "gift": '<rect x="3" y="8" width="18" height="4" rx="1"/><path d="M5 12v9h14v-9M12 8v13"/><path d="M12 8S9.5 8 8.3 6.8A2 2 0 0 1 11 4c1 .6 1 4 1 4zM12 8s2.5 0 3.7-1.2A2 2 0 0 0 13 4c-1 .6-1 4-1 4z"/>',
    "repeat": '<path d="M17 2l4 4-4 4"/><path d="M3 11V9a4 4 0 0 1 4-4h14M7 22l-4-4 4-4"/><path d="M21 13v2a4 4 0 0 1-4 4H3"/>',
    # people / support
    "user": '<circle cx="12" cy="8" r="4"/><path d="M20 21a8 8 0 0 0-16 0"/>',
    "chat": '<path d="M21 15a2 2 0 0 1-2 2H8l-5 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/>',
    "headset": '<path d="M3 12h3a2 2 0 0 1 2 2v3a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-5Zm18 0h-3a2 2 0 0 0-2 2v3a2 2 0 0 0 2 2h1a2 2 0 0 0 2-2v-5Z"/><path d="M21 12a9 9 0 0 0-18 0"/>',
    "mail": '<rect x="2" y="4" width="20" height="16" rx="2.5"/><path d="m3 7 9 6 9-6"/>',
    "ticket": '<path d="M3 9a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2 2 2 0 0 0 0 4 2 2 0 0 1-2 2H5a2 2 0 0 1-2-2 2 2 0 0 0 0-4z"/><path d="M13 7v10"/>',
    "send": '<path d="m22 2-7 20-4-9-9-4z"/><path d="M22 2 11 13"/>',
    # ui chrome
    "search": '<circle cx="11" cy="11" r="7"/><path d="m20 20-3.5-3.5"/>',
    "chevron-down": '<path d="m6 9 6 6 6-6"/>',
    "chevron-right": '<path d="m9 6 6 6-6 6"/>',
    "arrow-right": '<path d="M5 12h14M12 5l7 7-7 7"/>',
    "arrow-down": '<path d="M12 5v14M19 12l-7 7-7-7"/>',
    "external": '<path d="M15 3h6v6M10 14 21 3M21 14v5a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5"/>',
    "menu": '<path d="M4 6h16M4 12h16M4 18h16"/>',
    "moon": '<path d="M12 3a6 6 0 0 0 9 9 9 9 0 1 1-9-9Z"/>',
    "sun": '<circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4"/>',
    "plane": '<path d="M17.8 19.2 16 11l3.5-3.5a2.1 2.1 0 0 0-3-3L13 8 4.8 6.2a.6.6 0 0 0-.6 1L8 10l-2 2-2.5-.5a.5.5 0 0 0-.4.9L6 14.5 7.6 18a.5.5 0 0 0 .9-.4L8 15l2-2 2.8 3.8a.6.6 0 0 0 1-.6z"/>',
    "compass": '<circle cx="12" cy="12" r="10"/><path d="m16 8-2 6-6 2 2-6z"/>',
    "download": '<path d="M12 3v12M7 11l5 5 5-5"/><path d="M4 20h16"/>',
    "copy": '<rect x="9" y="9" width="12" height="12" rx="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/>',
    "star": '<path d="m12 3 2.7 5.6 6.1.9-4.4 4.3 1 6.1-5.4-2.9-5.4 2.9 1-6.1L3.2 9.5l6.1-.9z"/>',
    "sparkle": '<path d="M12 3v4M12 17v4M3 12h4M17 12h4M5.6 5.6l2.8 2.8M15.6 15.6l2.8 2.8M18.4 5.6l-2.8 2.8M8.4 15.6l-2.8 2.8"/>',
    "inbox": '<path d="M3 13h5l1.5 3h5L16 13h5"/><path d="M4.4 5.2 3 13v5a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-5l-1.4-7.8A2 2 0 0 0 17.6 4H6.4a2 2 0 0 0-2 1.2z"/>',
    "list": '<path d="M8 6h13M8 12h13M8 18h13M3.5 6h.01M3.5 12h.01M3.5 18h.01"/>',
    "hotspot": '<circle cx="12" cy="18" r="2"/><path d="M8.5 14.5a5 5 0 0 1 7 0M5.5 11.5a9 9 0 0 1 13 0"/>',
    "trash": '<path d="M3 6h18M8 6V4a1 1 0 0 1 1-1h6a1 1 0 0 1 1 1v2M6 6l1 14a2 2 0 0 0 2 2h6a2 2 0 0 0 2-2l1-14"/>',
    "logout": '<path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"/><path d="m16 17 5-5-5-5M21 12H9"/>',
}
_FILLED = {"star"}


@register.simple_tag
def icon(name, size=20, cls="", stroke=1.8):
    """Inline SVG by name. Unknown names render nothing rather than breaking a page."""
    path = _P.get(name)
    if not path:
        return ""
    fill, stroke_attr = ("currentColor", "none") if name in _FILLED else ("none", "currentColor")
    return mark_safe(  # noqa: S308 - paths are our own constants, never user input
        f'<svg class="ico {cls}" width="{size}" height="{size}" viewBox="0 0 24 24" '
        f'fill="{fill}" stroke="{stroke_attr}" stroke-width="{stroke}" '
        f'stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" '
        f'focusable="false">{path}</svg>'
    )


@register.simple_tag
def item_attrs(plan, list_id="", index=0):
    """data- attributes that let a click on a plan be reported as select_item.

    The payload is built here rather than in JavaScript so the item shape stays
    identical to the one the server sends with view_item_list and purchase; a
    mismatch would split the same plan into two rows in the GA4 reports."""
    from apps.common.analytics import plan_item

    payload = json.dumps(plan_item(plan, index=index), separators=(",", ":"))
    return format_html('data-item="{}" data-list="{}"', payload, list_id)


# --- Money -------------------------------------------------------------------
@register.filter
def data_size(mb):
    """Megabytes as something a person reads: "820 MB", "4.3 GB", "12 GB"."""
    if mb in (None, ""):
        return ""
    try:
        value = float(mb)
    except (TypeError, ValueError):
        return ""
    if value < 1024:
        return f"{value:.0f} MB"
    gb = value / 1024
    return f"{gb:.0f} GB" if abs(gb - round(gb)) < 0.05 else f"{gb:.1f} GB"


@register.filter
def usd(value):
    """$7.99 — two decimals, no locale surprises."""
    try:
        return f"${Decimal(str(value)).quantize(Decimal('0.01'))}"
    except Exception:  # noqa: BLE001
        return ""
