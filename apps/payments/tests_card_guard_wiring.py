"""That the guard is actually wired in — not that it works.

payguard has its own suite for whether the ladder and the signals are right.
What cannot be tested there is whether this product calls it, and what a
customer sees when it says no. Both halves of that have failed silently before:
a guard nobody calls looks identical to a guard that never fires, and a refusal
that surfaces as a 500 is worse than no refusal at all.
"""
from __future__ import annotations

from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase, override_settings
from payguard import record_card_failure
from payguard.models import CardCooldown

from apps.payments.services import open_card_sessions

User = get_user_model()


class GuardIsReachedTests(TestCase):
    def setUp(self):
        cache.clear()
        self.user = User.objects.create_user(email="buyer@example.com", password="x",
                                             email_verified=True)

    def auth(self):
        from rest_framework_simplejwt.tokens import RefreshToken

        token = RefreshToken.for_user(self.user).access_token
        return {"HTTP_AUTHORIZATION": f"Bearer {token}"}

    @override_settings(IN_APP_PAYMENTS=True)
    def test_a_cooled_down_account_gets_429_and_a_retry_after(self):
        # Four declines puts the account on the longest rung.
        for _ in range(4):
            record_card_failure(user=self.user, email=self.user.email)

        r = self.client.post("/api/v1/wallet/topup-sheet/", {"amount": "25.00"},
                             content_type="application/json", **self.auth())
        self.assertEqual(r.status_code, 429, r.content[:200])
        self.assertEqual(r.json().get("code"), "payment_cooldown")
        self.assertIn("Retry-After", r.headers)

    @override_settings(IN_APP_PAYMENTS=True)
    def test_the_refusal_leaves_no_half_written_topup_behind(self):
        # The guard runs before the row is created, so a refused attempt is not
        # something anyone has to reconcile later.
        from apps.wallet.models import BalanceTopUp

        for _ in range(4):
            record_card_failure(user=self.user, email=self.user.email)
        before = BalanceTopUp.objects.count()
        self.client.post("/api/v1/wallet/topup-sheet/", {"amount": "25.00"},
                         content_type="application/json", **self.auth())
        self.assertEqual(BalanceTopUp.objects.count(), before)

    def test_a_disposable_inbox_is_refused_before_anything_fails(self):
        burner = User.objects.create_user(email="x@mailinator.com", password="x",
                                          email_verified=True)
        from payguard import CardBlocked, card_risk_gate

        with self.assertRaises(CardBlocked):
            card_risk_gate(burner, client_ip="203.0.113.1", email=burner.email)


class OpenSessionCountTests(TestCase):
    """The velocity count is this product's job; payguard only judges it."""

    def setUp(self):
        self.user = User.objects.create_user(email="counter@example.com", password="x")

    def test_unfinished_stripe_checkouts_are_counted(self):
        from apps.payments.models import Payment

        for _ in range(3):
            Payment.objects.create(user=self.user, provider=Payment.Provider.STRIPE,
                                   status=Payment.Status.WAITING, amount_usd=Decimal("5.00"))
        self.assertEqual(open_card_sessions(self.user), 3)

    def test_a_settled_one_is_not(self):
        from apps.payments.models import Payment

        Payment.objects.create(user=self.user, provider=Payment.Provider.STRIPE,
                               status=Payment.Status.PAID, amount_usd=Decimal("5.00"))
        self.assertEqual(open_card_sessions(self.user), 0)

    def test_no_user_means_no_count_rather_than_an_error(self):
        self.assertEqual(open_card_sessions(None), 0)


class MigrationTests(TestCase):
    def test_payguard_tables_exist(self):
        # build.sh migrates on every deploy, so this is really asserting that
        # the app is in INSTALLED_APPS and its migration shipped with it.
        self.assertEqual(CardCooldown.objects.count(), 0)


class PermanentBlockTests(TestCase):
    """The step past the ladder: an identity that is not coming back.

    A cooldown is a wait and a block is a verdict, and the difference has to
    survive all the way to the customer. Telling somebody to try again in ten
    minutes when nothing will ever let them through is a support ticket; the
    reverse -- telling a customer whose card was declined twice that they are
    permanently banned -- is a lost customer.
    """

    def setUp(self):
        cache.clear()
        self.user = User.objects.create_user(email="carder@example.com", password="x",
                                             email_verified=True)

    def auth(self):
        from rest_framework_simplejwt.tokens import RefreshToken

        token = RefreshToken.for_user(self.user).access_token
        return {"HTTP_AUTHORIZATION": f"Bearer {token}"}

    @override_settings(IN_APP_PAYMENTS=True)
    def test_a_blocked_account_is_refused_without_a_time_to_come_back(self):
        from payguard import permanently_block

        permanently_block(user=self.user, email=self.user.email, reason="test")

        r = self.client.post("/api/v1/wallet/topup-sheet/", {"amount": "25.00"},
                             content_type="application/json", **self.auth())
        self.assertEqual(r.status_code, 403, r.content[:200])
        self.assertEqual(r.json().get("code"), "payment_blocked")
        self.assertNotIn(
            "Retry-After", r.headers,
            "a permanent block must not name a moment at which it lifts")

    @override_settings(IN_APP_PAYMENTS=True, CARD_PERMANENT_BLOCK_AFTER=8)
    def test_the_ladder_escalates_on_its_own_once_the_count_is_absurd(self):
        """Nobody mistypes a card eight times. Reaching that count without the
        attacker ever meeting a human decision is the point of the feature."""
        from payguard import is_permanently_blocked

        for _ in range(8):
            record_card_failure(user=self.user, email=self.user.email)

        self.assertTrue(is_permanently_blocked(user=self.user, email=self.user.email))
        r = self.client.post("/api/v1/wallet/topup-sheet/", {"amount": "25.00"},
                             content_type="application/json", **self.auth())
        self.assertEqual(r.status_code, 403)

    def test_an_ordinary_run_of_declines_is_still_only_a_wait(self):
        """The guard against over-reach. Four declines is the top of the ladder
        and must stay a cooldown -- a customer whose bank is being difficult has
        not done anything to be banned for."""
        from payguard import is_permanently_blocked

        for _ in range(4):
            record_card_failure(user=self.user, email=self.user.email)

        self.assertFalse(is_permanently_blocked(user=self.user, email=self.user.email))

    def test_radar_calling_it_fraud_skips_the_count_entirely(self):
        """A stolen card is a verdict on the first attempt. Waiting for eight
        would be allowing seven more."""
        from payguard import is_permanently_blocked

        from apps.payments.services import _is_confirmed_fraud

        self.assertTrue(_is_confirmed_fraud(
            {"last_payment_error": {"decline_code": "stolen_card"}}))
        self.assertTrue(_is_confirmed_fraud(
            {"charges": {"data": [{"outcome": {"type": "blocked",
                                               "reason": "highest_risk_level"}}]}}))
        # An ordinary decline is not a verdict, and must fall through to the
        # ladder rather than banning somebody whose balance was short.
        self.assertFalse(_is_confirmed_fraud(
            {"last_payment_error": {"decline_code": "insufficient_funds"}}))
        self.assertFalse(_is_confirmed_fraud({}))
        self.assertFalse(is_permanently_blocked(user=self.user, email=self.user.email))

    def test_an_address_is_never_put_on_the_list(self):
        """Shared addresses are why CARD_IP_COOLDOWN_FACTOR is a quarter. A
        forever-ban on an airport's NAT address bans the airport, and the
        travellers it bans are exactly this product's customers."""
        from payguard import is_permanently_blocked, permanently_block

        permanently_block(user=self.user, email=self.user.email,
                          ip="198.51.100.9", reason="test")
        self.assertFalse(
            is_permanently_blocked(ip="198.51.100.9"),
            "an address must not be bannable for good while CARD_PERMANENT_BLOCK_IP is off")
        self.assertTrue(is_permanently_blocked(user=self.user))
