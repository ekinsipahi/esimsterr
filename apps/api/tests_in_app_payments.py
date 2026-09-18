"""What the app takes a card for, and what it does not.

One card flow, and it adds balance. Every plan in the catalogue -- and there are
thousands -- is bought by spending that balance, which is a deduction from credit
the customer already owns rather than a payment transaction. So there is one
till in the app, it is the shortest path in it, and the store policy argument is
about one thing instead of two.

Worth a test rather than a comment, because both halves fail silently and in
opposite directions. A build that offers a card the server will refuse is a dead
end dressed as an offer. A server that accepts a payment while the app hides the
button is a kill switch that kills nothing. Both look fine from the outside, and
the only place the truth is written down is the endpoint's answer.

Every class overrides the settings it depends on. These used to read whatever
.env happened to hold, which meant the suite proved something different on a
developer's machine than in CI -- and the thing it proved was about money.
"""
from __future__ import annotations

import json
from decimal import Decimal
from unittest import mock

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase, override_settings

from apps.catalog.models import Country, Plan
from apps.common.models import RemoteConfig

User = get_user_model()

# Stripe is configured as far as these tests are concerned; nothing here talks
# to it. The card flow's own behaviour is covered in apps/payments.
STRIPE_READY = override_settings(STRIPE_PUBLISHABLE_KEY="pk_test_x",
                                 STRIPE_SECRET_KEY="sk_test_x")


class InAppBase(TestCase):
    def setUp(self):
        # RemoteConfig caches for a minute, and the cache outlives the database
        # rollback between tests -- so a class that switches card payments off
        # was deciding the answer for every class that ran after it.
        cache.clear()

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

    def config(self):
        return self.client.get("/api/v1/config/").json()

    def plan_sheet(self):
        return self.client.post(
            "/api/v1/pay/sheet/",
            data=json.dumps({"plan_id": self.plan.pk, "consent": True,
                             "email": "buyer@example.com", "stripe_version": "2024-06-20"}),
            content_type="application/json", HTTP_X_SUPPORT_ID="ESM-TSTA-BCDE")

    def topup_sheet(self, amount="25.00"):
        return self.client.post(
            "/api/v1/wallet/topup-sheet/",
            data=json.dumps({"amount": amount, "stripe_version": "2024-06-20"}),
            content_type="application/json", **self.bearer())


@STRIPE_READY
@override_settings(IN_APP_PAYMENTS=True, IN_APP_PLAN_PAYMENTS=False)
class TheShippedArrangementTests(InAppBase):
    """Balance is bought with a card in the app; plans are bought with balance."""

    def test_the_app_is_told_both_answers_separately(self):
        """One flag for both was the bug. Off, it sent somebody buying credit
        into a browser mid-purchase; on, it offered a card for a plan as well."""
        config = self.config()
        self.assertTrue(config["in_app_payments"])
        self.assertFalse(config["in_app_plan_payments"])

    def test_the_publishable_key_is_handed_out(self):
        """Top-up needs it. Withholding it would leave the app unable to open a
        payment sheet the server is willing to serve."""
        self.assertEqual(self.config()["stripe_publishable_key"], "pk_test_x")

    def test_buying_a_plan_with_a_card_is_refused_by_the_server(self):
        """The part that matters. Hiding a button is a decoration; this is the
        refusal, and it holds for a build that ignored the flag."""
        response = self.plan_sheet()
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()["code"], "in_app_unavailable")

    def test_no_payment_row_is_left_behind_by_the_refusal(self):
        """A refusal that has already created a Payment leaves a waiting row
        nothing will ever settle, and those are what an operator has to tell
        apart from a genuinely stuck payment."""
        from apps.payments.models import Payment

        self.plan_sheet()
        self.assertEqual(Payment.objects.count(), 0)

    def test_adding_balance_with_a_card_goes_through(self):
        """The other half, and the half that used to be refused with it.

        Patched at the Stripe boundary rather than mocked wholesale, so the
        endpoint, the top-up row and the Payment row are all real.
        """
        from apps.payments import stripe_client
        from apps.payments.models import Payment
        from apps.wallet.models import BalanceTopUp

        with mock.patch.object(stripe_client, "ensure_customer", return_value="cus_x"), \
             mock.patch.object(stripe_client, "create_payment_intent",
                               return_value={"id": "pi_x", "client_secret": "pi_x_secret"}), \
             mock.patch.object(stripe_client, "ephemeral_key",
                               return_value={"secret": "ek_x"}):
            response = self.topup_sheet()

        self.assertEqual(response.status_code, 201, response.content[:300])
        body = response.json()
        self.assertEqual(body["payment_intent_client_secret"], "pi_x_secret")
        self.assertEqual(body["publishable_key"], "pk_test_x")
        self.assertEqual(BalanceTopUp.objects.count(), 1)
        self.assertEqual(Payment.objects.get().status, Payment.Status.WAITING)

    def test_the_website_still_takes_payments(self):
        """Closing the app's card path for plans must not close the till. The
        web checkout is a different code path and stays open."""
        self.assertEqual(self.client.get(f"/checkout/{self.plan.pk}/").status_code, 200)

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


@STRIPE_READY
@override_settings(IN_APP_PAYMENTS=True, IN_APP_PLAN_PAYMENTS=True)
class PlanPaymentsSwitchedBackOnTests(InAppBase):
    """The setting has to mean something in both positions, or it is a comment.

    Nobody is shipping this, but a flag that has only ever been tested in one
    position is a flag that does not work: the day it is flipped is the day the
    code behind it runs for the first time.
    """

    def test_the_app_is_told_it_may_offer_a_card_for_a_plan(self):
        self.assertTrue(self.config()["in_app_plan_payments"])

    def test_the_endpoint_serves_a_sheet(self):
        from apps.payments import stripe_client

        with mock.patch.object(stripe_client, "ensure_customer", return_value="cus_x"), \
             mock.patch.object(stripe_client, "create_payment_intent",
                               return_value={"id": "pi_x", "client_secret": "pi_x_secret"}), \
             mock.patch.object(stripe_client, "ephemeral_key",
                               return_value={"secret": "ek_x"}):
            response = self.plan_sheet()
        self.assertEqual(response.status_code, 201, response.content[:300])
        self.assertEqual(response.json()["payment_intent_client_secret"], "pi_x_secret")


@STRIPE_READY
@override_settings(IN_APP_PAYMENTS=False, IN_APP_PLAN_PAYMENTS=True)
class NoCardAtAllTests(InAppBase):
    """The wider setting has to contain the narrower one.

    IN_APP_PLAN_PAYMENTS left on while the card flow is switched off entirely
    must not reopen the plan endpoint. This is the configuration somebody
    arrives at by turning the app's card flow off in a hurry and not noticing
    the second line.
    """

    def test_the_plan_endpoint_stays_shut(self):
        self.assertEqual(self.plan_sheet().status_code, 503)

    def test_topping_up_is_shut_too(self):
        response = self.topup_sheet()
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()["code"], "in_app_unavailable")

    def test_and_no_key_is_handed_out(self):
        """Nothing to initialise Stripe with, so a build that ignored the flags
        could not present a payment sheet either."""
        config = self.config()
        self.assertEqual(config["stripe_publishable_key"], "")
        self.assertFalse(config["in_app_payments"])
        self.assertFalse(config["in_app_plan_payments"])


@STRIPE_READY
@override_settings(IN_APP_PAYMENTS=True)
class RemoteSwitchTests(TestCase):
    """The incident lever, which used not to pull anything.

    `enabled()` read the setting and Stripe's configuration and stopped there, so
    turning card payments off during an incident hid a button in the app and left
    the endpoint accepting payments. A switch that stops nothing is worse than no
    switch: somebody flips it and believes the problem is contained.
    """

    def setUp(self):
        cache.clear()

    def test_the_switch_closes_the_endpoint(self):
        from apps.payments.inapp import enabled

        config = RemoteConfig.current()
        config.card_payments = False
        config.save()
        self.assertFalse(enabled())

    @override_settings(IN_APP_PLAN_PAYMENTS=True)
    def test_it_closes_the_plan_path_with_it(self):
        """One lever for the card, not one per thing bought with it. An operator
        stopping card payments at 3am should not have to find two switches."""
        from apps.payments.inapp import plan_payments_enabled

        config = RemoteConfig.current()
        config.card_payments = False
        config.save()
        self.assertFalse(plan_payments_enabled())

    def test_and_opens_it_again(self):
        """Closing has to be reversible, or the lever is a fuse."""
        from apps.payments import inapp

        config = RemoteConfig.current()
        config.card_payments = True
        config.save()
        with mock.patch.object(inapp.stripe_client, "configured", return_value=True):
            self.assertTrue(inapp.enabled())

    def test_an_unreadable_config_does_not_close_the_till(self):
        """A database or cache problem must not stop payments. The switch is for
        somebody deciding to stop them, not for the infrastructure deciding."""
        from apps.payments import inapp

        with mock.patch.object(inapp.stripe_client, "configured", return_value=True), \
             mock.patch("apps.common.models.RemoteConfig.current",
                        side_effect=RuntimeError("database is away")):
            self.assertTrue(inapp.enabled())
