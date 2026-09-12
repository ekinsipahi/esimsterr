"""Give every destination page unique, factual copy and its own title tag.

Why this exists: 148 country pages generated from one template, with only the
country name swapped, is the textbook shape of a doorway cluster. Google treats
it as one page repeated and ranks none of them.

The fix here is not to write 148 essays. It is to make each page say things that
are only true of that destination, drawn from data we already hold: which
carriers the eSIM actually roams onto, what the entry price is, whether an
unlimited option exists, how long the plans run, which regional bundles cover the
country, and which neighbours sit next to it. Two countries with different
carriers and different prices end up with materially different text.

Sentence order and phrasing are chosen from a deterministic hash of the ISO code,
so the copy does not read as one paragraph with nouns swapped, and re-running the
command is stable rather than churning the pages.

Hand-written copy still beats this. Anything an operator writes into a Country's
`intro` by hand is preserved: pass --overwrite only when you mean to discard it.
"""
from __future__ import annotations

import hashlib
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db.models import Max, Min

from apps.catalog.models import Country

# Titles are hard-capped: Google truncates around 60 characters, and a cut title
# loses exactly the part we care about, the price.
TITLE_MAX = 60
DESC_MAX = 155


def _pick(seed: str, options: list) -> str:
    """Deterministic choice, stable across runs for a given country."""
    h = int(hashlib.sha256(seed.encode()).hexdigest()[:8], 16)
    return options[h % len(options)]


def _fmt(amount) -> str:
    return f"${Decimal(amount).quantize(Decimal('0.01'))}"


def _article(name: str) -> str:
    """"a" or "an" for a country name. Vowel letters are not enough on their own
    ("a Ukraine eSIM" is right, "an Ukraine eSIM" is not), so the exceptions are
    listed rather than inferred."""
    first = name[:1].upper()
    if first in "AEIOU" and not name.lower().startswith(("eu", "u")):
        return "An"
    return "A"


def _join(names: list[str], limit: int = 3) -> str:
    names = [n for n in names if n][:limit]
    if not names:
        return ""
    if len(names) == 1:
        return names[0]
    return ", ".join(names[:-1]) + " and " + names[-1]


class Command(BaseCommand):
    help = "Write unique intro copy, title tags and meta descriptions for destination pages."

    def add_arguments(self, parser):
        parser.add_argument("--overwrite", action="store_true",
                            help="Replace copy that already exists, including hand-written intros")
        parser.add_argument("--only", default="", help="Comma-separated ISO2 codes")

    def handle(self, *args, **opts):
        qs = Country.objects.filter(is_active=True)
        if opts["only"]:
            wanted = [c.strip().upper() for c in opts["only"].split(",") if c.strip()]
            qs = qs.filter(iso2__in=wanted)

        written = skipped = 0
        for country in qs.prefetch_related("regions"):
            fields = self._compose(country)
            updates = []
            for name, value in fields.items():
                if value and (opts["overwrite"] or not getattr(country, name)):
                    setattr(country, name, value)
                    updates.append(name)
            if updates:
                country.save(update_fields=updates)
                written += 1
            else:
                skipped += 1

        self.stdout.write(self.style.SUCCESS(
            f"Destination copy: {written} updated, {skipped} already had copy "
            f"(use --overwrite to replace)"
        ))

    # ------------------------------------------------------------------
    def _compose(self, country: Country) -> dict:
        plans = list(country.plans.live())
        if not plans:
            return {}

        seed = country.iso2
        price = country.min_price_usd or min(p.price for p in plans)
        agg = country.plans.live().aggregate(shortest=Min("days"), longest=Max("days"))
        operators = country.operator_list
        regions = list(country.regions.filter(is_active=True))
        neighbours = list(
            Country.objects.filter(is_active=True, continent=country.continent)
            .exclude(pk=country.pk).order_by("-is_popular", "name")
            .values_list("name", flat=True)[:3]
        )
        biggest = max((p for p in plans if p.data_gb), key=lambda p: p.data_gb, default=None)

        return {
            "intro": self._intro(country, seed, price, operators, plans, agg, regions,
                                 neighbours, biggest),
            "seo_title": self._title(country, price),
            "seo_description": self._description(country, seed, price, operators, regions),
        }

    def _intro(self, country, seed, price, operators, plans, agg, regions, neighbours, biggest):
        name = country.name
        carrier_count = len(operators)

        # Opening: what the eSIM connects to. This is the sentence that differs
        # most between countries, because the carrier list genuinely differs.
        if carrier_count >= 2:
            opener = _pick(seed + "open", [
                f"{_article(name)} {name} eSIM puts your phone on {_join(operators)} the moment you land, "
                f"at the same local rates a resident pays.",
                f"Your data in {name} runs over {_join(operators)}, so you get local speeds "
                f"instead of a roaming surcharge bolted onto your home plan.",
                f"We buy {name} data wholesale from {_join(operators)} and resell it as an "
                f"eSIM you install before you fly.",
            ])
        elif carrier_count == 1:
            opener = (f"{_article(name)} {name} eSIM connects to {operators[0]}, the network our "
                      f"supply runs on there, at local data rates rather than roaming rates.")
        else:
            opener = (f"{_article(name)} {name} eSIM connects to the strongest local network "
                      f"available at your destination, at local rather than roaming data rates.")

        # Price sentence, carrying the real entry point.
        entry = _pick(seed + "price", [
            f"Plans start at {_fmt(price)}.",
            f"The cheapest plan on this page is {_fmt(price)}.",
            f"Entry price is {_fmt(price)}.",
        ])

        # Shape of the catalogue for this country.
        shortest, longest = agg["shortest"], agg["longest"]
        if country.has_unlimited:
            shape = (f"There are {len(plans)} plans in total, from {shortest}-day top-ups to "
                     f"{longest}-day cover, including unlimited data for travellers who would "
                     f"rather not watch a counter.")
        elif biggest is not None:
            shape = (f"There are {len(plans)} plans in total, from {shortest}-day top-ups up to "
                     f"{biggest.data_label} over {longest} days.")
        else:
            shape = f"There are {len(plans)} plans in total, running from {shortest} to {longest} days."

        # Regional cross-sell only when a bundle genuinely covers this country.
        if regions:
            region = regions[0]
            cross = (f"If {name} is one stop of several, the {region.name} plan covers "
                     f"{region.country_count} countries on the same profile, so you do not "
                     f"reinstall anything at a border.")
        elif neighbours:
            cross = (f"Travelling on to {_join(neighbours)} as well? Check the regional plans "
                     f"before buying country by country.")
        else:
            cross = ("Buying for a single destination is usually cheapest when you are only "
                     "visiting one country.")

        closer = _pick(seed + "close", [
            "Install it at home on Wi-Fi. The clock only starts when the eSIM first connects "
            "on arrival, so nothing is wasted in transit.",
            "The QR code arrives the moment you pay, and the validity window starts on first "
            "connection at your destination rather than at purchase.",
            "Your own SIM stays in the phone and keeps your number reachable; the eSIM only "
            "carries data.",
        ])

        order = _pick(seed + "order", ["abcd", "abdc", "acbd"])
        parts = {"a": f"{opener} {entry}", "b": shape, "c": cross, "d": closer}
        return " ".join(parts[k] for k in order)

    def _title(self, country, price):
        """Lead with the destination, carry the price. Trim, never truncate mid-word."""
        name = country.name
        candidates = [
            f"{name} eSIM from just {_fmt(price)} - instant data",
            f"{name} eSIM from just {_fmt(price)} - no roaming",
            f"{name} eSIM - travel data from just {_fmt(price)}",
            f"{name} eSIM from just {_fmt(price)}",
        ]
        for c in candidates:
            if len(c) <= TITLE_MAX:
                return c
        return candidates[-1][:TITLE_MAX].rsplit(" ", 1)[0]

    def _description(self, country, seed, price, operators, regions):
        name = country.name
        carriers = _join(operators, 2)
        options = []
        if carriers:
            options.append(
                f"Prepaid {name} eSIM data on {carriers} from {_fmt(price)}. Instant QR "
                f"delivery, no roaming fees, keep your own number."
            )
        options.append(
            f"Buy a {name} travel eSIM from {_fmt(price)}. Local 4G and 5G data, delivered "
            f"instantly by QR code, no passport and no contract."
        )
        if country.has_unlimited:
            options.append(
                f"{name} eSIM plans from {_fmt(price)}, including unlimited data. Install "
                f"before you fly, connect the moment you land."
            )
        text = _pick(seed + "desc", options)
        if len(text) > DESC_MAX:
            text = text[:DESC_MAX].rsplit(" ", 1)[0].rstrip(",.") + "."
        return text
