"""The structured data every public page publishes.

Worth testing rather than eyeballing, because it fails silently. A malformed
block is invisible in the browser, invisible in the logs, and surfaces weeks
later as a drop in Search Console that nobody connects to the template edit that
caused it.

The claims here are also claims about money: a Product node is what puts a price
in a search result, and a price that disagrees with the page is worse than no
price at all.
"""
from __future__ import annotations

import json
import re
from decimal import Decimal

from django.test import TestCase, override_settings
from django.urls import reverse

from apps.blog.models import Post
from apps.catalog.models import Country, Plan

BLOCK = re.compile(r'<script type="application/ld\+json">(.*?)</script>', re.S)


def blocks(html: str) -> list[dict]:
    """Every JSON-LD block on the page, parsed."""
    return [json.loads(raw) for raw in BLOCK.findall(html)]


def of_type(payloads, kind: str):
    return [p for p in payloads if p.get("@type") == kind]


class StructuredDataBase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.country = Country.objects.create(
            iso2="TR", name="Turkey", slug="turkey", is_active=True)
        for gb, days, price in ((1, 7, "1.49"), (5, 30, "6.99"), (20, 30, "18.99")):
            Plan.objects.create(
                country=cls.country, provider_plan_id=f"tr{gb}",
                provider_name=f"Turkey {gb}GB", data_gb=Decimal(gb), days=days,
                cost_amount=Decimal("1.00"), price_usd=Decimal(price),
                is_active=True, kind="country")
        cls.post = Post.objects.create(
            title="Getting online in Turkey", slug="turkey-guide", is_published=True,
            excerpt="What to do at the airport.", body="…")

    def page(self, path: str) -> list[dict]:
        response = self.client.get(path)
        self.assertEqual(response.status_code, 200, path)
        return blocks(response.content.decode())


class EveryPageTests(StructuredDataBase):
    def paths(self):
        return [
            "/",
            reverse("destinations"),
            reverse("faq"),
            reverse("coupons"),
            self.country.get_absolute_url(),
            self.post.get_absolute_url(),
        ]

    def test_every_block_on_every_page_is_valid_json(self):
        """The failure this catches is silent everywhere else."""
        for path in self.paths():
            with self.subTest(path=path):
                response = self.client.get(path)
                for raw in BLOCK.findall(response.content.decode()):
                    json.loads(raw)   # raises, and names the page, if malformed

    def test_every_block_declares_its_context(self):
        """A node without @context is not structured data, it is a JSON comment."""
        for path in self.paths():
            with self.subTest(path=path):
                for payload in self.page(path):
                    self.assertIn("@context", payload, payload.get("@type"))

    def test_the_organisation_is_described_once_and_referenced_after_that(self):
        """One node, pointed at from everywhere. Repeating it in full on every
        page gives a crawler several companies with the same name instead of one
        with several pages."""
        for path in self.paths():
            with self.subTest(path=path):
                payloads = self.page(path)
                described = [p for p in payloads
                             if p.get("@type") == "Organization" and "name" in p]
                self.assertEqual(len(described), 1)
                self.assertTrue(described[0]["@id"].endswith("#org"))

    def test_every_page_carries_the_website_node(self):
        for path in self.paths():
            with self.subTest(path=path):
                site = of_type(self.page(path), "WebSite")
                self.assertEqual(len(site), 1)
                self.assertEqual(site[0]["publisher"]["@id"],
                                 of_type(self.page(path), "Organization")[0]["@id"])


class BreadcrumbTests(StructuredDataBase):
    def test_a_page_with_a_visible_trail_publishes_it(self):
        """These used to be rendered and never published: the trail was on the
        page and the BreadcrumbList was on three SEO pages only."""
        payloads = self.page(self.country.get_absolute_url())
        crumbs = of_type(payloads, "BreadcrumbList")
        self.assertEqual(len(crumbs), 1)
        names = [i["name"] for i in crumbs[0]["itemListElement"]]
        self.assertEqual(names, ["Home", "Destinations", "Turkey"])

    def test_positions_are_contiguous_from_one(self):
        crumbs = of_type(self.page(self.country.get_absolute_url()), "BreadcrumbList")[0]
        positions = [i["position"] for i in crumbs["itemListElement"]]
        self.assertEqual(positions, list(range(1, len(positions) + 1)))

    def test_the_last_crumb_needs_no_link(self):
        """It is the page you are on, and schema.org does not want an item on it."""
        crumbs = of_type(self.page(self.country.get_absolute_url()), "BreadcrumbList")[0]
        self.assertNotIn("item", crumbs["itemListElement"][-1])

    def test_a_page_without_a_trail_publishes_none(self):
        self.assertEqual(of_type(self.page("/"), "BreadcrumbList"), [])


class ProductTests(StructuredDataBase):
    def product(self):
        found = of_type(self.page(self.country.get_absolute_url()), "Product")
        self.assertEqual(len(found), 1)
        return found[0]

    def test_the_price_range_is_the_real_one(self):
        """The number in the search result. If it disagrees with the page, the
        click arrives expecting a price we do not sell."""
        offers = self.product()["offers"]
        self.assertEqual(offers["lowPrice"], "1.49")
        self.assertEqual(offers["highPrice"], "18.99")
        self.assertEqual(offers["offerCount"], 3)

    def test_the_seller_is_the_organisation_rather_than_a_name(self):
        product = self.product()
        org = of_type(self.page(self.country.get_absolute_url()), "Organization")[0]
        self.assertEqual(product["brand"]["@id"], org["@id"])
        self.assertEqual(product["offers"]["offers"][0]["seller"]["@id"], org["@id"])

    def test_a_destination_with_no_plans_publishes_no_product(self):
        """An empty AggregateOffer is a shop window with nothing in it."""
        empty = Country.objects.create(iso2="AQ", name="Nowhere", slug="nowhere",
                                       is_active=True)
        self.assertEqual(of_type(self.page(empty.get_absolute_url()), "Product"), [])


@override_settings(DEBUG=False, CANONICAL_HOST="esimsterr.com",
                   ALLOWED_HOSTS=["esimsterr.com", "alias.example.com", "testserver"])
class CanonicalUrlTests(StructuredDataBase):
    def test_urls_use_the_canonical_host_even_on_an_alias(self):
        """A page reached on an alias host was publishing offer URLs on that
        host while its own canonical link pointed elsewhere, which reads as two
        pages selling the same thing -- and the duplicate is the one that ranks.
        """
        response = self.client.get(self.country.get_absolute_url(),
                                   HTTP_HOST="alias.example.com")
        # The alias redirects to the canonical host; follow it and check what the
        # page publishes about itself either way.
        if response.status_code in (301, 302):
            response = self.client.get(self.country.get_absolute_url(),
                                       HTTP_HOST="esimsterr.com")
        payloads = blocks(response.content.decode())
        product = of_type(payloads, "Product")[0]
        for offer in product["offers"]["offers"]:
            self.assertTrue(offer["url"].startswith("https://esimsterr.com/"), offer["url"])
        for crumb in of_type(payloads, "BreadcrumbList")[0]["itemListElement"]:
            if "item" in crumb:
                self.assertTrue(crumb["item"].startswith("https://esimsterr.com/"))


class ArticleTests(StructuredDataBase):
    def test_a_post_is_published_by_the_same_organisation(self):
        payloads = self.page(self.post.get_absolute_url())
        article = of_type(payloads, "Article")[0]
        org = of_type(payloads, "Organization")[0]
        self.assertEqual(article["publisher"]["@id"], org["@id"])
        self.assertEqual(article["author"]["@id"], org["@id"])

    def test_it_carries_both_dates(self):
        article = of_type(self.page(self.post.get_absolute_url()), "Article")[0]
        self.assertIn("datePublished", article)
        self.assertIn("dateModified", article)
