"""Clause and document types, surface filtering, and version hashing.

The point of splitting legal text into clauses is that the same sentence is
often true on more than one surface and differently true on others. "You buy on
the website" is a plain fact on the web and a compliance-critical statement
inside an iOS app. Forking the documents per platform is how you end up with a
privacy policy that contradicts your App Store data disclosure, so instead each
clause declares the surfaces it applies to and a document is *composed* for the
surface asking for it.

Every document carries an explicit version and effective date. They are not
derived from the file's modification time or from today's date: a legal page
that says "last updated today" every day tells the reader nothing and tells a
regulator less. `check_legal` compares a hash of the source text against a
checked-in lock file, so text cannot change without the version changing.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import date

WEB = "web"
IOS = "ios"
ANDROID = "android"
ALL_SURFACES = (WEB, IOS, ANDROID)
APP_SURFACES = (IOS, ANDROID)


@dataclass(frozen=True)
class Clause:
    """One numbered section of a document.

    `title` may be None for a lead-in paragraph that carries no heading.
    `surfaces` narrows where the clause appears; the default is everywhere.
    """
    id: str
    title: str | None
    body: tuple
    surfaces: tuple = ALL_SURFACES
    anchor: str | None = None

    def applies_to(self, surface: str) -> bool:
        return surface in self.surfaces

    @property
    def slug(self) -> str:
        return self.anchor or self.id

    def sources(self) -> tuple:
        out = [self.title] if self.title else []
        for block in self.body:
            out.extend(block.sources())
        return tuple(out)


@dataclass(frozen=True)
class Document:
    """A legal document: metadata plus an ordered list of clause ids."""
    slug: str
    title: str
    summary: str
    version: str
    effective: date
    clauses: tuple
    url_name: str | None = None
    surfaces: tuple = ALL_SURFACES
    numbered: bool = True
    # Shown in the site footer and the /legal/ index. A document can be live
    # and linked from another document without being listed on its own.
    listed: bool = True
    seo_title: str = ""

    def applies_to(self, surface: str) -> bool:
        return surface in self.surfaces


@dataclass
class RenderedClause:
    number: str
    slug: str
    title: str | None
    blocks: list


def resolve(document: Document, library: dict, surface: str = WEB) -> list:
    """The clauses of this document that apply to `surface`, in order."""
    out = []
    for cid in document.clauses:
        clause = library.get(cid)
        if clause is None:
            raise KeyError(f"{document.slug!r} references unknown clause {cid!r}")
        if clause.applies_to(surface):
            out.append(clause)
    return out


def numbered(document: Document, clauses: list) -> list:
    """Attach display numbers. Lead-in clauses (no title) are never numbered,
    so the first heading is always "1" however many introductions precede it."""
    rendered, n = [], 0
    for clause in clauses:
        if clause.title and document.numbered:
            n += 1
            number = str(n)
        else:
            number = ""
        rendered.append(RenderedClause(
            number=number, slug=clause.slug, title=clause.title,
            blocks=list(clause.body),
        ))
    return rendered


def content_hash(document: Document, library: dict, surface: str = WEB) -> str:
    """A stable fingerprint of a document's source text on one surface.

    Taken over the untranslated strings and the clause order, so it changes when
    the meaning changes and not when a translation lands or a reader switches
    language. Truncated to 16 hex characters: long enough to be unambiguous for
    this many documents, short enough to sit in an email or a database column
    without wrapping.
    """
    h = hashlib.sha256()
    h.update(f"{document.slug}|{surface}".encode())
    for clause in resolve(document, library, surface):
        h.update(b"\x00" + clause.id.encode())
        for src in clause.sources():
            h.update(b"\x01" + (src or "").encode())
    return h.hexdigest()[:16]
