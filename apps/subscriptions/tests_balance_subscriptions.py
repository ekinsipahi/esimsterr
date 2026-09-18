"""Subscriptions paid out of the customer's balance.

WHY THESE ARE WORTH THE LENGTH. This is the only recurring debit in the codebase
we operate ourselves. A card subscription can be reasoned about by reading
Stripe's dashboard; this one only exists in our own tables, charges on a
schedule nobody is watching, and its failure modes are all quiet. Billing the
same period twice, billing a cancelled line, provisioning an eSIM that was never
paid for, or holding a line open for ever for somebody who stopped topping up --
none of those raise anything. They show up as a number that is wrong.

Provisioning is deliberately not executed. `start_cycle` schedules fulfilment on
commit, and running it would call the provider and spend real wholesale credit.
These tests assert the order is booked and the money moved; what fulfilment does
with the order is apps.orders' business and is tested there.
"""
from __future__ import annotations

import json
from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.utils import timezone

from apps.catalog.models import Plan, Region
from apps.orders.models import Order
from apps.payments.models import Payment
from apps.subscriptions.models import Subscription, SubscriptionCycle
from apps.subscriptions.services import (PAST_DUE_GRACE, SubscriptionNotAvailable,
                                         cancel_at_period_end, cancel_now,
                                         due_for_renewal, renew_with_balance,
                                         start_with_balance, subscription_price)
from apps.wallet.models import InsufficientBalance, Wallet, WalletTransaction

User = get_user_model()


class BalanceSubscriptionBase(TestCase):
    @classmethod
    def setUpTestData(cls):
        # Europe unlimited monthly: one of the four on the menu, priced at
        # $29.99 in apps.subscriptions.catalogue.
        cls.region = Region.objects.create(key="europe", name="Europe", slug="europe",
                                           is_active=True, country_names="France,Spain")
        cls.plan = Plan.objects.create(
            region=cls.region, provider_plan_id="eu-unl-30", provider_name="Europe unlimited",
            data_gb=None, is_unlimited=True, days=30, cost_amount=Decimal("21.46"),
            price_usd=Decimal("34.99"), is_active=True, kind="region")
        # A plan that is not on the subscription menu: 5 GB, not unlimited.
        cls.bucket = Plan.objects.create(
            region=cls.region, provider_plan_id="eu-5gb-30", provider_name="Europe 5GB",
            data_gb=Decimal("5"), days=30, cost_amount=Decimal("4.00"),
            price_usd=Decimal("9.99"), is_active=True, kind="region")
        cls.user = User.objects.create_user(email="sub@example.com", password="x",
                                            email_verified=True)

    def setUp(self):
        self.price = subscription_price(self.plan)

    def fund(self, amount, user=None):
        return Wallet.credit(user or self.user, Decimal(str(amount)), description="test")

    def balance(self, user=None):
        return Wallet.for_user(user or self.user).balance_usd

    def bearer(self, user=None):
        from rest_framework_simplejwt.tokens import RefreshToken

        token = RefreshToken.for_user(user or self.user).access_token
        return {"HTTP_AUTHORIZATION": f"Bearer {token}"}


class StartingTests(BalanceSubscriptionBase):
    def test_the_first_period_comes_off_the_balance(self):
        self.fund("50.00")
        sub = start_with_balance(self.user, self.plan)

        self.assertEqual(sub.funding, Subscription.Funding.BALANCE)
        self.assertEqual(sub.status, Subscription.Status.ACTIVE)
        self.assertEqual(self.balance(), Decimal("50.00") - self.price)

    def test_it_books_one_order_for_one_period(self):
        """The cycle is a real Order, like every other sale, so revenue and
        fulfilment keep one reporting surface."""
        self.fund("50.00")
        sub = start_with_balance(self.user, self.plan)

        self.assertEqual(SubscriptionCycle.objects.filter(subscription=sub).count(), 1)
        order = Order.objects.get()
        self.assertEqual(order.amount_usd, self.price)
        self.assertEqual(order.kind, Order.Kind.NEW)

    def test_the_period_runs_for_the_plan_duration(self):
        self.fund("50.00")
        sub = start_with_balance(self.user, self.plan)
        days = (sub.current_period_end - timezone.now()).days
        self.assertEqual(days, 29)   # 30 days, minus the seconds since it started

    def test_spending_credit_is_not_recorded_as_a_second_payment(self):
        """The dollar was counted as revenue when the balance was bought.

        Writing a Payment row here as well would count it twice, and the second
        count is the one that makes a month's takings look better than they were.
        """
        self.fund("50.00")
        start_with_balance(self.user, self.plan)

        self.assertEqual(Payment.objects.count(), 0)
        movement = WalletTransaction.objects.get(kind=WalletTransaction.Kind.SPEND)
        self.assertEqual(-movement.amount_usd, self.price)

    def test_a_short_balance_creates_absolutely_nothing(self):
        """The failure that matters. A subscription row left behind by a debit
        that did not happen is a line that renews for ever without a first
        payment -- and it looks active on every screen we have."""
        self.fund("5.00")
        with self.assertRaises(InsufficientBalance):
            start_with_balance(self.user, self.plan)

        self.assertEqual(Subscription.objects.count(), 0)
        self.assertEqual(Order.objects.count(), 0)
        self.assertEqual(SubscriptionCycle.objects.count(), 0)
        self.assertEqual(self.balance(), Decimal("5.00"))

    def test_the_same_plan_cannot_be_subscribed_to_twice(self):
        """Two subscriptions for one line is two charges and two eSIMs for
        something the customer thought was one renewal."""
        self.fund("100.00")
        start_with_balance(self.user, self.plan)
        with self.assertRaises(SubscriptionNotAvailable):
            start_with_balance(self.user, self.plan)
        self.assertEqual(Subscription.objects.count(), 1)

    def test_a_plan_that_is_not_on_the_menu_is_refused(self):
        """The menu is four plans. A plan id is not a menu, so the rule is
        enforced here rather than only in the listing."""
        self.fund("100.00")
        with self.assertRaises(SubscriptionNotAvailable):
            start_with_balance(self.user, self.bucket)

    def test_a_cancelled_subscription_does_not_block_a_new_one(self):
        """Somebody who cancels and comes back is a customer, not a duplicate."""
        self.fund("100.00")
        sub = start_with_balance(self.user, self.plan)
        cancel_now(sub)
        again = start_with_balance(self.user, self.plan)
        self.assertNotEqual(sub.pk, again.pk)


class RenewalTests(BalanceSubscriptionBase):
    def due(self, sub, *, days_ago=0):
        """Make this subscription's period have ended."""
        Subscription.objects.filter(pk=sub.pk).update(
            current_period_end=timezone.now() - timedelta(days=days_ago))
        sub.refresh_from_db()
        return sub

    def test_a_due_subscription_is_charged_again(self):
        self.fund("100.00")
        sub = self.due(start_with_balance(self.user, self.plan))

        cycle = renew_with_balance(sub)

        self.assertIsNotNone(cycle)
        self.assertEqual(self.balance(), Decimal("100.00") - self.price * 2)
        sub.refresh_from_db()
        self.assertEqual(sub.status, Subscription.Status.ACTIVE)
        self.assertGreater(sub.current_period_end, timezone.now())

    def test_a_renewal_tops_the_same_line_up_rather_than_issuing_a_second_esim(self):
        """A customer who renews should not have to install a second profile,
        and we should not pay the provider for one."""
        self.fund("100.00")
        sub = self.due(start_with_balance(self.user, self.plan))
        # Bind an eSIM as a real first cycle's fulfilment would have done.
        from apps.orders.models import Esim

        esim = Esim.objects.create(user=self.user, order=Order.objects.first(),
                                   iccid="8900000000000000001")
        Subscription.objects.filter(pk=sub.pk).update(esim=esim)
        sub.refresh_from_db()

        renew_with_balance(sub)
        self.assertEqual(Order.objects.latest("created_at").kind, Order.Kind.TOPUP)

    def test_a_renewal_that_finds_no_money_marks_the_line_past_due(self):
        self.fund(self.price)             # exactly one period
        sub = self.due(start_with_balance(self.user, self.plan))

        self.assertIsNone(renew_with_balance(sub))

        sub.refresh_from_db()
        self.assertEqual(sub.status, Subscription.Status.PAST_DUE)
        self.assertIn("Balance is", sub.last_error)

    def test_and_charges_nothing_and_provisions_nothing(self):
        """The dangerous half of a failed renewal: an order booked against money
        that was never taken is an eSIM we buy and never sell."""
        self.fund(self.price)
        sub = self.due(start_with_balance(self.user, self.plan))
        renew_with_balance(sub)

        self.assertEqual(Order.objects.count(), 1)          # the first period only
        self.assertEqual(SubscriptionCycle.objects.count(), 1)
        self.assertEqual(self.balance(), Decimal("0.00"))

    def test_topping_up_after_a_failure_renews_on_the_next_run(self):
        """Nobody should have to email support to restart a line they have paid
        for. The next scheduled run is the whole recovery."""
        self.fund(self.price)
        sub = self.due(start_with_balance(self.user, self.plan))
        renew_with_balance(sub)

        self.fund("50.00")
        self.assertIn(sub, list(due_for_renewal()))
        self.assertIsNotNone(renew_with_balance(sub))
        sub.refresh_from_db()
        self.assertEqual(sub.status, Subscription.Status.ACTIVE)

    def test_a_line_left_unpaid_past_the_grace_is_cancelled(self):
        """A subscription nobody is funding cannot stay open for ever: it shows
        as active to the customer and renews the moment they top up for
        something else entirely."""
        self.fund(self.price)
        sub = self.due(start_with_balance(self.user, self.plan))
        renew_with_balance(sub)                                  # -> past_due

        self.due(sub, days_ago=PAST_DUE_GRACE.days + 1)
        renew_with_balance(sub)

        sub.refresh_from_db()
        self.assertEqual(sub.status, Subscription.Status.CANCELED)

    def test_a_cancelled_at_period_end_line_is_stopped_rather_than_charged(self):
        """The customer said stop. Taking one more month is the single worst
        thing this code could do."""
        self.fund("100.00")
        sub = self.due(start_with_balance(self.user, self.plan))
        cancel_at_period_end(sub)
        sub.refresh_from_db()

        self.assertIsNone(renew_with_balance(sub))
        sub.refresh_from_db()
        self.assertEqual(sub.status, Subscription.Status.CANCELED)
        self.assertEqual(self.balance(), Decimal("100.00") - self.price)

    def test_a_line_that_is_not_due_is_left_alone(self):
        self.fund("100.00")
        start_with_balance(self.user, self.plan)
        self.assertEqual(list(due_for_renewal()), [])

    def test_a_card_subscription_is_never_touched_by_this(self):
        """Stripe owns that mandate. Charging the wallet for it as well would
        bill the same month twice, once on each rail."""
        self.fund("100.00")
        Subscription.objects.create(
            user=self.user, plan=self.plan, price_usd=self.price, interval_days=30,
            funding=Subscription.Funding.CARD, status=Subscription.Status.ACTIVE,
            current_period_end=timezone.now() - timedelta(days=1))
        self.assertEqual(list(due_for_renewal()), [])


class RenewalCommandTests(BalanceSubscriptionBase):
    def test_a_second_run_does_not_bill_the_month_again(self):
        """Cron overlaps. An hourly command that double-charges on a slow run is
        the kind of bug a customer finds before we do."""
        self.fund("100.00")
        sub = start_with_balance(self.user, self.plan)
        Subscription.objects.filter(pk=sub.pk).update(
            current_period_end=timezone.now() - timedelta(minutes=1))

        call_command("renew_subscriptions", verbosity=0)
        after_first = self.balance()
        call_command("renew_subscriptions", verbosity=0)

        self.assertEqual(self.balance(), after_first)
        self.assertEqual(SubscriptionCycle.objects.count(), 2)

    def test_a_dry_run_moves_no_money(self):
        self.fund("100.00")
        sub = start_with_balance(self.user, self.plan)
        Subscription.objects.filter(pk=sub.pk).update(
            current_period_end=timezone.now() - timedelta(minutes=1))
        before = self.balance()

        call_command("renew_subscriptions", "--dry-run", verbosity=0)
        self.assertEqual(self.balance(), before)

    def test_one_customer_with_no_money_does_not_stop_the_rest(self):
        """It is a loop over other people's subscriptions."""
        broke = User.objects.create_user(email="broke@example.com", password="x",
                                         email_verified=True)
        self.fund(self.price, user=broke)
        self.fund("100.00")

        for user in (broke, self.user):
            sub = start_with_balance(user, self.plan)
            Subscription.objects.filter(pk=sub.pk).update(
                current_period_end=timezone.now() - timedelta(minutes=1))

        call_command("renew_subscriptions", verbosity=0)

        self.assertEqual(Subscription.objects.get(user=broke).status,
                         Subscription.Status.PAST_DUE)
        self.assertEqual(Subscription.objects.get(user=self.user).status,
                         Subscription.Status.ACTIVE)


@override_settings(SUBSCRIPTIONS_ENABLED=True)
class ApiTests(BalanceSubscriptionBase):
    def start(self, plan=None, consent=True, user=None):
        return self.client.post(
            "/api/v1/subscriptions/start/",
            data=json.dumps({"plan_id": (plan or self.plan).pk, "consent": consent}),
            content_type="application/json", **self.bearer(user))

    def test_the_app_can_subscribe_from_balance(self):
        self.fund("50.00")
        response = self.start()

        self.assertEqual(response.status_code, 201, response.content[:300])
        body = response.json()
        self.assertEqual(body["subscription"]["status"], "active")
        self.assertEqual(body["subscription"]["funding"], "balance")
        # The new balance travels back, so the screen behind the sheet is right
        # without a second round trip.
        self.assertEqual(body["wallet"]["balance_usd"],
                         f"{Decimal('50.00') - self.price:.2f}")

    def test_a_short_balance_is_answered_with_the_shortfall(self):
        """"Add $12.48 and this works" is a screen. "Something went wrong" is
        a support ticket."""
        self.fund("17.51")
        response = self.start()

        self.assertEqual(response.status_code, 402)
        body = response.json()
        self.assertEqual(body["code"], "insufficient_balance")
        self.assertEqual(body["shortfall_usd"], f"{self.price - Decimal('17.51'):.2f}")

    def test_consent_is_required_before_anything_is_delivered(self):
        self.fund("50.00")
        self.assertEqual(self.start(consent=False).status_code, 400)
        self.assertEqual(Subscription.objects.count(), 0)

    def test_signing_in_is_required(self):
        """A recurring debit needs an account to belong to and to be cancelled
        from."""
        response = self.client.post(
            "/api/v1/subscriptions/start/",
            data=json.dumps({"plan_id": self.plan.pk, "consent": True}),
            content_type="application/json")
        self.assertIn(response.status_code, (401, 403))

    def test_the_list_shows_running_lines_first(self):
        self.fund("100.00")
        self.start()
        cancelled = Subscription.objects.create(
            user=self.user, plan=self.bucket, price_usd=Decimal("9.99"), interval_days=30,
            funding=Subscription.Funding.BALANCE, status=Subscription.Status.CANCELED)

        rows = self.client.get("/api/v1/subscriptions/", **self.bearer()).json()
        self.assertEqual([r["status"] for r in rows], ["active", "canceled"])
        self.assertEqual(rows[1]["id"], str(cancelled.pk))

    def test_cancelling_stops_the_next_charge_and_keeps_the_month(self):
        self.fund("100.00")
        sub_id = self.start().json()["subscription"]["id"]

        response = self.client.post(f"/api/v1/subscriptions/{sub_id}/cancel/",
                                    content_type="application/json", **self.bearer())
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["cancel_at_period_end"])
        self.assertEqual(response.json()["status"], "active")

    def test_a_cancellation_can_be_undone_while_the_period_runs(self):
        self.fund("100.00")
        sub_id = self.start().json()["subscription"]["id"]
        self.client.post(f"/api/v1/subscriptions/{sub_id}/cancel/",
                         content_type="application/json", **self.bearer())

        response = self.client.post(f"/api/v1/subscriptions/{sub_id}/resume/",
                                    content_type="application/json", **self.bearer())
        self.assertFalse(response.json()["cancel_at_period_end"])

    def test_nobody_can_cancel_a_subscription_that_is_not_theirs(self):
        """Ownership is checked in the query rather than after it: a 404 tells
        the caller nothing about whether that id exists."""
        self.fund("100.00")
        sub_id = self.start().json()["subscription"]["id"]
        stranger = User.objects.create_user(email="stranger@example.com", password="x")

        response = self.client.post(f"/api/v1/subscriptions/{sub_id}/cancel/",
                                    content_type="application/json",
                                    **self.bearer(stranger))
        self.assertEqual(response.status_code, 404)
        self.assertFalse(Subscription.objects.get(pk=sub_id).cancel_at_period_end)

    def test_a_card_subscription_is_sent_to_the_website_to_be_cancelled(self):
        """Cancelling it here would stop nothing at Stripe and tell the customer
        it had stopped -- which is how a line keeps charging after it was
        cancelled."""
        sub = Subscription.objects.create(
            user=self.user, plan=self.plan, price_usd=self.price, interval_days=30,
            funding=Subscription.Funding.CARD, status=Subscription.Status.ACTIVE)

        response = self.client.post(f"/api/v1/subscriptions/{sub.pk}/cancel/",
                                    content_type="application/json", **self.bearer())
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["code"], "manage_on_web")

    @override_settings(SUBSCRIPTIONS_ENABLED=False)
    def test_the_whole_feature_has_a_switch(self):
        self.fund("100.00")
        self.assertEqual(self.start().status_code, 503)
