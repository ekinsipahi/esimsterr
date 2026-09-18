"""The app takes no payment.

A purchase inside the app is a deduction from credit the customer already owns.
Every payment -- buying that credit included -- happens on the website. That
leaves one place where money is taken: one place to get right, one place to
debug, and one place a store can have an opinion about.

Worth a test rather than a comment, because the failure is silent in both
directions. A build that offers a card the server will refuse is a dead end
dressed as an offer; a server that accepts one while the app hides the button is
a kill switch that kills nothing. Both look fine from the outside.
"""
from __future__ import annotations

import json
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings

from apps.catalog.models import Country, Plan
from apps.common.models import RemoteConfig

User = get_user_model()


class InAppPaymentTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.country = Country.objects.create(iso2="TR", name="Turkey", slug="turkey",
                                             is_active=True)
        cls.plan = Plan.objects.create(
            country=cls.country, provider_plan_id="tr1", provider_name="Turkey 1GB",
            data_gb=Decimal("1"), days=7, cost_amount=Decimal("1.00"),
            price_usd=Decimal("1.49"), is_active=True, kind="country")
        cls.customer = User.objects.create_user(email="buyer@example.com", password="x",
                                                email_verified=True)

    def bearer(self, user=None):
        """The API authenticates with JWT, not the session, so force_login does
        nothing here -- a request without this header is simply anonymous."""
        from rest_framework_simplejwt.tokens import RefreshToken

        token = RefreshToken.for_user(user or self.customer).access_token
        return {"HTTP_AUTHORIZATION": f"Bearer {token}"}

    def sheet(self):
        return self.client.post(
            "/api/v1/pay/sheet/",
            data=json.dumps({"plan_id": self.plan.pk, "consent": True,
                             "email": "buyer@example.com", "stripe_version": "2024-06-20"}),
            content_type="application/json", HTTP_X_SUPPORT_ID="ESM-TEST-0001")

    def test_the_app_is_told_there_are_no_in_app_payments(self):
        config = self.client.get("/api/v1/config/").json()
        self.assertFalse(config["in_app_payments"])

    def test_no_publishable_key_is_handed_out(self):
        """Nothing to initialise Stripe with, so a build that ignored the flag
        could not present a payment sheet either."""
        self.assertEqual(self.client.get("/api/v1/config/").json()["stripe_publishable_key"], "")

    def test_the_endpoint_refuses_rather_than_the_button_being_hidden(self):
        """The part that matters. Hiding a button is a decoration; this is the
        refusal."""
        response = self.sheet()
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()["code"], "in_app_unavailable")

    def test_topping_up_in_the_app_is_refused_the_same_way(self):
        response = self.client.post(
            "/api/v1/wallet/topup-sheet/",
            data=json.dumps({"amount": "25.00", "stripe_version": "2024-06-20"}),
            content_type="application/json", **self.bearer())
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()["code"], "in_app_unavailable")

    def test_the_website_still_takes_payments(self):
        """Turning the app's card path off must not close the till. The web
        checkout is a different code path and stays open."""
        response = self.client.get(f"/checkout/{self.plan.pk}/")
        self.assertEqual(response.status_code, 200)

    def test_spending_balance_is_not_a_payment_and_still_works(self):
        """The whole point of the arrangement: the app can still sell."""
        from apps.wallet.models import Wallet

        Wallet.credit(self.customer, Decimal("20.00"), description="test")
        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.post(
                "/api/v1/orders/pay-with-balance/",
                data=json.dumps({"plan_id": self.plan.pk, "consent": True}),
                content_type="application/json", **self.bearer())
        self.assertEqual(response.status_code, 201, response.content[:300])
        self.assertEqual(response.json()["wallet"]["balance_usd"], "18.51")


@override_settings(IN_APP_PAYMENTS=True)
class RemoteSwitchTests(TestCase):
    """The incident lever, which used not to pull anything.

    `enabled()` read the setting and Stripe's configuration and stopped there, so
    turning card payments off during an incident hid a button in the app and left
    the endpoint accepting payments. A switch that stops nothing is worse than no
    switch: somebody flips it and believes the problem is contained.
    """

    def test_the_switch_closes_the_endpoint(self):
        from apps.payments.inapp import enabled

        config = RemoteConfig.current()
        config.card_payments = False
        config.save()
        self.assertFalse(enabled())

    @override_settings(STRIPE_PUBLISHABLE_KEY="pk_test_x")
    def test_and_opens_it_again(self):
        """Closing has to be reversible, or the lever is a fuse."""
        from unittest import mock

        from apps.payments import inapp

        config = RemoteConfig.current()
        config.card_payments = True
        config.save()
        with mock.patch.object(inapp.stripe_client, "configured", return_value=True):
            self.assertTrue(inapp.enabled())

    @override_settings(STRIPE_PUBLISHABLE_KEY="pk_test_x")
    def test_an_unreadable_config_does_not_close_the_till(self):
        """A database or cache problem must not stop payments. The switch is for
        somebody deciding to stop them, not for the infrastructure deciding."""
        from unittest import mock

        from apps.payments import inapp

        with mock.patch.object(inapp.stripe_client, "configured", return_value=True), \
             mock.patch("apps.common.models.RemoteConfig.current",
                        side_effect=RuntimeError("database is away")):
            self.assertTrue(inapp.enabled())
