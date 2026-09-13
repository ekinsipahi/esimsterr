"""The small markup language the legal clauses are written in.

Legal text needs three things that plain strings do not give you: it has to be
translatable as whole sentences, it has to link to other clauses and pages
without hard-coding a URL into the sentence, and it must never be able to inject
markup. So a clause body is a list of blocks, each block holds source text, and
that text is escaped on render with only a fixed set of tokens resolved:

    [[doc:refund]]              link to a legal document, using its own title
    [[doc:refund|refund terms]] the same, with your own label
    [[url:compatible_devices]]  link to a named Django URL, label required
    [[mail]]                    the support address as a mailto link
    **emphasis**                <strong>
    {site} {company} {support}  substituted from settings

Nothing else in the source survives as markup, so a translator cannot break a
page and a clause cannot smuggle a script tag in.

The source strings are wrapped in `_`, which is `gettext_noop`: xgettext still
extracts them into the .po files, but the value kept in memory is the original
English. That matters because the document version hash is taken over these
source strings -- a hash over translated output would change with the reader's
language, and a legal version that differs per visitor is worthless.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from django.conf import settings
from django.urls import NoReverseMatch, reverse
from django.utils.html import escape
from django.utils.safestring import mark_safe
from django.utils.translation import gettext

TOKEN = re.compile(r"\[\[(doc|url|mail)(?::([a-z0-9_\-]+))?(?:\|([^\]]+))?\]\]")
BOLD = re.compile(r"\*\*(.+?)\*\*")


def _substitutions() -> dict:
    return {
        "site": settings.SITE_NAME,
        "company": settings.COMPANY_LEGAL_NAME or settings.SITE_NAME,
        "support": settings.SUPPORT_EMAIL,
        "host": settings.CANONICAL_HOST,
        "jurisdiction": settings.LEGAL_JURISDICTION,
        "courts": settings.LEGAL_COURTS,
        "entity_address": settings.COMPANY_ADDRESS,
    }


def _link(href: str, label: str) -> str:
    return f'<a href="{escape(href)}">{escape(label)}</a>'


def inline(source: str) -> str:
    """Escape one source string and resolve its tokens. Returns safe HTML."""
    from apps.legal.documents import document_url, get_document

    text = gettext(source)
    try:
        text = text.format(**_substitutions())
    except (KeyError, IndexError, ValueError):
        # A translation with a broken placeholder must not take the page down;
        # showing the unsubstituted sentence is the lesser failure.
        pass

    out, last = [], 0
    for m in TOKEN.finditer(text):
        out.append(escape(text[last:m.start()]))
        kind, target, label = m.group(1), m.group(2), m.group(3)
        if kind == "mail":
            addr = settings.SUPPORT_EMAIL
            out.append(_link(f"mailto:{addr}", label or addr))
        elif kind == "doc":
            doc = get_document(target)
            if doc:
                out.append(_link(document_url(doc), label or gettext(doc.title)))
            else:
                out.append(escape(label or target or ""))
        else:  # url
            try:
                out.append(_link(reverse(target), label or target))
            except NoReverseMatch:
                out.append(escape(label or ""))
        last = m.end()
    out.append(escape(text[last:]))

    html = "".join(out)
    return BOLD.sub(r"<strong>\1</strong>", html)


# --- block types -------------------------------------------------------------
@dataclass(frozen=True)
class Block:
    """Base: every block knows its own source strings, for hashing."""

    def sources(self) -> tuple[str, ...]:
        raise NotImplementedError

    def render(self) -> str:
        raise NotImplementedError


@dataclass(frozen=True)
class P(Block):
    text: str

    def sources(self):
        return (self.text,)

    def render(self):
        return mark_safe(f"<p>{inline(self.text)}</p>")


@dataclass(frozen=True)
class H(Block):
    """A sub-heading inside a clause."""
    text: str

    def sources(self):
        return (self.text,)

    def render(self):
        return mark_safe(f"<h3>{inline(self.text)}</h3>")


@dataclass(frozen=True)
class UL(Block):
    items: tuple

    def __init__(self, *items):
        object.__setattr__(self, "items", tuple(items))

    def sources(self):
        return self.items

    def render(self):
        rows = "".join(f"<li>{inline(i)}</li>" for i in self.items)
        return mark_safe(f"<ul>{rows}</ul>")


@dataclass(frozen=True)
class OL(UL):
    def render(self):
        rows = "".join(f"<li>{inline(i)}</li>" for i in self.items)
        return mark_safe(f"<ol>{rows}</ol>")


@dataclass(frozen=True)
class Callout(Block):
    """A boxed sentence: used where a rule is easy to miss and expensive to miss."""
    text: str

    def sources(self):
        return (self.text,)

    def render(self):
        return mark_safe(f'<div class="legal-callout">{inline(self.text)}</div>')


@dataclass(frozen=True)
class Table(Block):
    """A fixed-column table. Legal tables are for facts (cookies, providers,
    retention periods), where prose would only hide the detail."""
    head: tuple
    rows: tuple

    def __init__(self, head, rows):
        object.__setattr__(self, "head", tuple(head))
        object.__setattr__(self, "rows", tuple(tuple(r) for r in rows))

    def sources(self):
        return tuple(self.head) + tuple(c for row in self.rows for c in row)

    def render(self):
        th = "".join(f"<th>{inline(h)}</th>" for h in self.head)
        body = "".join(
            "<tr>" + "".join(f"<td>{inline(c)}</td>" for c in row) + "</tr>"
            for row in self.rows
        )
        return mark_safe(
            f'<div class="legal-table-wrap"><table class="legal-table">'
            f"<thead><tr>{th}</tr></thead><tbody>{body}</tbody></table></div>"
        )
