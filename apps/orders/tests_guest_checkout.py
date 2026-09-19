"""Buying requires an account.

WHY THIS IS TESTED RATHER THAN TRUSTED. It is a door being closed, and a door
that looks closed is the dangerous kind. The checkout page hiding itself proves
nothing: what matters is that the POST which creates the order and starts the
payment cannot be reached, because that is the request an automated buyer
actually sends.

The other half is the round trip. Somebody who has typed a coupon, chosen a
gift address or picked a line to top up and is then asked to sign in must come
back to the same purchase, not to the front page. A login wall that loses the
basket is a login wall that loses the sale.
"""
from __future__ import annotations

from decimal import Decimal
from unittest import mock

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase, override_settings

from apps.catalog.models import Country, Plan
from apps.common.models import RemoteConfig
from apps.orders.models import Order

User = get_user_model()


class GuestCheckoutBase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.country = Country.objects.create(iso2="TR", name="Turkey", slug="turkey",
                                             is_active=True)
        cls.plan = Plan.objects.create(
            country=cls.country, provider_plan_id="tr1", provider_name="Turkey 1GB",
            data_gb=Decimal("1"), days=7, cost_amount=Decimal("1.00"),
            price_usd=Decimal("1.49"), is_active=True, kind="country")
        cls.customer = User.objects.create_user(email="buyer@example.com", password="secret-x",
                                                email_verified=True)

    def setUp(self):
        # RemoteConfig caches for a minute and the cache outlives the database
        # rollback between tests, so a class that flips a switch would otherwise
        # decide the answer for every class that runs after it.
        cache.clear()

    @property
    def url(self):
        return f"/checkout/{self.plan.pk}/"

    def buy(self, **extra):
        return self.client.post(self.url, {
            "email": "someone@example.com",
            "method": "stripe",
            "digital_consent": "on",
            **extra,
        })


@override_settings(GUEST_CHECKOUT=False)
class ClosedTests(GuestCheckoutBase):
    def test_the_page_asks_a_signed_out_visitor_to_sign_in(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response["Location"].startswith("/login/"))

    def test_the_post_that_creates_the_order_is_refused_too(self):
        """The one that matters. A hidden page is a decoration; this is the
        refusal, and it holds for a client that never loaded the page."""
        response = self.buy()
        self.assertEqual(response.status_code, 302)
        self.assertEqual(Order.objects.count(), 0)

    def test_the_purchase_is_carried_through_the_login_page(self):
        """A coupon typed, a gift address entered and a line chosen to top up
        all live in the query string. Losing them loses the sale."""
        response = self.client.get(f"{self.url}?coupon=SUMMER&esim=42&src=app")
        self.assertIn("coupon%3DSUMMER", response["Location"])
        self.assertIn("esim%3D42", response["Location"])

    def test_it_says_why_rather_than_just_demanding_a_password(self):
        response = self.client.get(self.url, follow=True)
        self.assertContains(response, "Sign in to buy")

    def test_a_missing_plan_still_says_so(self):
        """A 404 dressed as a login prompt sends somebody hunting for their
        password over a plan that does not exist."""
        self.assertEqual(self.client.get("/checkout/999999/").status_code, 404)

    def test_a_signed_in_customer_buys_as_before(self):
        self.client.force_login(self.customer)
        self.assertEqual(self.client.get(self.url).status_code, 200)

    def test_the_remote_switch_cannot_open_it_again(self):
        """The switch closes; it does not open. An operator cannot turn guest
        buying back on against the setting, which is the whole point of ANDing
        them rather than picking whichever says yes."""
        from apps.orders.services import guest_checkout_allowed

        config = RemoteConfig.current()
        config.guest_checkout = True
        config.save()
        self.assertFalse(guest_checkout_allowed())


@override_settings(GUEST_CHECKOUT=True)
class OpenAgainTests(GuestCheckoutBase):
    """The setting has to mean something in both positions, or it is a comment.

    Nobody is shipping this, but a flag only ever tested in one position is a
    flag that does not work: the day it is flipped is the day the code behind
    it runs for the first time.
    """

    def test_a_guest_reaches_the_page(self):
        self.assertEqual(self.client.get(self.url).status_code, 200)

    def test_the_incident_switch_closes_it(self):
        """This used to stop nothing at all: `guest_checkout` was published to
        the app and enforced nowhere, so flipping it hid a button and left the
        website selling."""
        config = RemoteConfig.current()
        config.guest_checkout = False
        config.save()

        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response["Location"].startswith("/login/"))

    def test_an_unreadable_config_does_not_close_the_till(self):
        """A database or cache problem must not stop sales. The switch is for
        somebody deciding to stop them, not for the infrastructure deciding."""
        from apps.orders.services import guest_checkout_allowed

        with mock.patch("apps.common.models.RemoteConfig.current",
                        side_effect=RuntimeError("database is away")):
            self.assertTrue(guest_checkout_allowed())
