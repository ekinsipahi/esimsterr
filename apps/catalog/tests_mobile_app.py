"""The app's own page.

Most of what this page is for cannot be seen by looking at it. It exists to be
the thing the Play listing points back at, which means the parts that matter to
a crawler -- the structured data, the canonical address, the install link -- are
exactly the parts that can break without anyone noticing: the page still looks
right, and the reason it was built quietly stops working.

The screenshots get their own test for a different reason. They are captures of
a build, and a build changes. One of them already went stale once: the set
shipped to Play still shows a subscriptions section that was taken out of the
app, and publishing those would have advertised something we do not sell.
"""
from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path

from django.conf import settings
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.catalog.views import APP_SHOTS


class PageTests(TestCase):
    def setUp(self):
        self.url = reverse("mobile_app")

    def test_it_loads_and_links_to_the_listing(self):
        r = self.client.get(self.url)
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, settings.PLAY_STORE_URL)

    def test_the_store_link_is_derived_when_nothing_is_configured(self):
        """An empty PLAY_STORE_URL is read everywhere as "there is no app", so
        shipping the listing and leaving the setting blank would have taken the
        download button off its own page."""
        self.assertTrue(settings.PLAY_STORE_URL.endswith(settings.ANDROID_PACKAGE_NAME))

    def test_it_is_reachable_from_the_navigation(self):
        """A page nothing links to collects no authority and no visitors."""
        body = self.client.get("/").content.decode()
        self.assertIn(self.url, body)

    def test_it_is_in_the_sitemap(self):
        body = self.client.get("/sitemap.xml").content.decode()
        if "sitemap" in body and self.url not in body:
            # A sitemap index: follow it to the section holding the static pages.
            body = self.client.get("/sitemap-static.xml").content.decode()
        self.assertIn(self.url, body)


class StructuredDataTests(TestCase):
    """What actually carries the Play listing's weight across. Without it the
    two are a page and an unrelated outbound link."""

    @classmethod
    def setUpTestData(cls):
        # A real plan, because the offer block says what the free app then
        # sells and an empty catalogue would quietly skip the half of it that
        # stops "price 0" being read as the whole story.
        from apps.catalog.models import Country, Plan

        country = Country.objects.create(iso2="TR", name="Turkey", slug="turkey",
                                         is_active=True)
        Plan.objects.create(country=country, provider_plan_id="tr1",
                            provider_name="Turkey 1GB", data_gb=Decimal(1), days=7,
                            cost_amount=Decimal("1.00"), price_usd=Decimal("1.49"),
                            is_active=True, kind="country")

    def setUp(self):
        self.node = self._node(self.client.get(reverse("mobile_app")).content.decode())

    @staticmethod
    def _node(body):
        import re
        for block in re.findall(r'<script type="application/ld\+json">(.*?)</script>', body, re.S):
            data = json.loads(block)
            if data.get("@type") == "MobileApplication":
                return data
        raise AssertionError("no MobileApplication block on the page")

    def test_it_names_the_app_and_where_to_install_it(self):
        self.assertEqual(self.node["installUrl"], settings.PLAY_STORE_URL)
        self.assertIn(settings.ANDROID_PACKAGE_NAME, self.node["installUrl"])

    def test_it_publishes_itself_under_the_canonical_address(self):
        """A page that claims one address while linking to another reads as two
        pages, and the duplicate is the one that ranks."""
        self.assertEqual(self.node["url"], f"{settings.SITE_URL.rstrip('/')}{reverse('mobile_app')}")

    def test_it_claims_no_rating_it_does_not_have(self):
        """Google will show a rating if one is published. The only honest value
        today is none, and inventing one is a manual action waiting to happen."""
        self.assertNotIn("aggregateRating", self.node)
        self.assertNotIn("reviewCount", self.node)

    def test_the_download_is_free_and_says_what_is_not(self):
        """Price 0 on its own describes an app that sells nothing."""
        self.assertEqual(self.node["offers"]["price"], "0")
        self.assertIn("Free download", self.node["offers"]["description"])
        self.assertIn("$1.49", self.node["offers"]["description"])


class ScreenshotTests(TestCase):
    def test_every_screenshot_on_the_page_exists(self):
        """A missing one is a broken image in the hero, which is the first thing
        anyone arriving from Play would see."""
        for src, _alt, _caption in APP_SHOTS:
            with self.subTest(shot=src):
                self.assertTrue((Path(settings.BASE_DIR) / "static" / src).is_file(), src)

    def test_they_are_small_enough_to_be_in_a_hero(self):
        """They are decoration on a page whose job is a download button. A
        megabyte of screenshots on a phone on airport wifi is the download that
        does not happen."""
        for src, _alt, _caption in APP_SHOTS:
            with self.subTest(shot=src):
                kb = (Path(settings.BASE_DIR) / "static" / src).stat().st_size / 1024
                self.assertLess(kb, 120, f"{src} is {kb:.0f} KB")

    def test_each_one_is_described(self):
        """Alt text that repeats the heading tells a screen reader nothing."""
        for src, alt, caption in APP_SHOTS:
            with self.subTest(shot=src):
                self.assertTrue(alt and alt != caption, src)


class BonusTierTests(TestCase):
    @override_settings(WALLET_BONUS_TIERS="5:0,10:0,25:2,200:36")
    def test_the_page_quotes_the_tiers_the_checkout_actually_pays(self):
        """Read from the same setting rather than written into the page. A
        marketing page promising a bonus the product does not pay is the kind of
        thing nobody notices until a customer does."""
        body = self.client.get(reverse("mobile_app")).content.decode()
        self.assertIn("+8%", body)
        self.assertIn("+18%", body)

    @override_settings(WALLET_BONUS_TIERS="5:0,10:0")
    def test_nothing_is_shown_when_no_tier_pays_a_bonus(self):
        """A section headed "the more you add, the more we add" above a row of
        "+0%" argues against itself."""
        body = self.client.get(reverse("mobile_app")).content.decode()
        self.assertNotIn("bonus-rail", body)
