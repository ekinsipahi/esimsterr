"""What stops a card tester, and what lets a customer through.

Both halves matter and they pull against each other. A rule strict enough to
stop a script is strict enough to turn away somebody whose first card was
declined, and the tests that only prove the blocking half will happily let that
ship.
"""
from __future__ import annotations

import time
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase, override_settings
from django.utils import timezone

from apps.payments import card_guard as guard

User = get_user_model()

SETTINGS = dict(
    CARD_GUARD_ENABLED=True,
    CARD_GUARD_WINDOW_SECONDS=3600,
    CARD_GUARD_COOLDOWN_LADDER="0,30,120,600,3600",
    CARD_GUARD_BLOCK_SECONDS=3600,
    CARD_GUARD_USER_CARDS=3,
    CARD_GUARD_EMAIL_CARDS=3,
    CARD_GUARD_IP_CARDS=8,
    CARD_GUARD_CARD_FAILURES=4,
    CARD_GUARD_IP_ATTEMPTS=40,
    CARD_GUARD_FRESH_ACCOUNT_MINUTES=0,      # off unless a test asks for it
    CARD_GUARD_BLOCK_DISPOSABLE_EMAIL=True,
)


@override_settings(**SETTINGS)
class CardGuardTests(TestCase):
    def setUp(self):
        cache.clear()
        self.user = User.objects.create_user(email="buyer@example.com", password="x")
        # Old enough that the fresh-account rung never fires by accident.
        User.objects.filter(pk=self.user.pk).update(
            date_joined=timezone.now() - timedelta(days=30))
        self.user.refresh_from_db()
        self.ip = "203.0.113.9"

    def fail(self, fingerprint="", user=None, ip=None):
        guard.record_failure(user or self.user, ip or self.ip,
                             (user or self.user).email, fingerprint=fingerprint)

    # ---- the customer having a bad minute --------------------------------
    def test_one_decline_costs_nothing(self):
        # The commonest reason for a single decline is a typo. Making somebody
        # wait for that is a lost sale, not a defence.
        self.fail()
        guard.check(self.user, self.ip, self.user.email)

    def test_a_card_that_works_clears_what_came_before_it(self):
        self.fail(); self.fail()
        with self.assertRaises(guard.CardTestingBlocked):
            guard.check(self.user, self.ip, self.user.email)
        guard.record_success(self.user, self.ip, self.user.email)
        guard.check(self.user, self.ip, self.user.email)

    # ---- the ladder -------------------------------------------------------
    def test_the_wait_grows_with_each_decline(self):
        waits = []
        for _ in range(4):
            self.fail()
            try:
                guard.check(self.user, self.ip, self.user.email)
                waits.append(0)
            except guard.CardTestingBlocked as e:
                waits.append(e.retry_after)
        # 0, then 30s, then 2 min, then 10 min -- each step strictly longer.
        self.assertEqual(waits[0], 0)
        self.assertEqual(waits[1:], sorted(waits[1:]))
        self.assertGreater(waits[-1], waits[1])

    # ---- the signature that matters --------------------------------------
    def test_four_different_cards_from_one_account_is_blocked(self):
        # The scenario this whole module exists for: declined, try another,
        # declined, try another. A person does not own four cards they expect
        # to fail; a list being worked through looks exactly like this.
        for fingerprint in ("fpA", "fpB", "fpC", "fpD"):
            self.fail(fingerprint=fingerprint)
        with self.assertRaises(guard.CardTestingBlocked) as caught:
            guard.check(self.user, self.ip, self.user.email)
        self.assertIn("different cards", str(caught.exception))

    def test_the_same_card_retried_is_not_mistaken_for_a_list(self):
        # Two declines on one card is a bad card, not an attack. It still costs
        # a rung on the ladder; it must not cost the flat hour.
        self.fail(fingerprint="fpA")
        self.fail(fingerprint="fpA")
        with self.assertRaises(guard.CardTestingBlocked) as caught:
            guard.check(self.user, self.ip, self.user.email)
        self.assertNotIn("different cards", str(caught.exception))

    def test_one_card_declined_over_and_over_is_refused_everywhere(self):
        for _ in range(4):
            self.fail(fingerprint="fpZ")
        with self.assertRaises(guard.CardTestingBlocked):
            guard.check_card("fpZ")
        guard.check_card("fpOther")          # a different card is unaffected

    # ---- evasion ----------------------------------------------------------
    def test_a_new_account_does_not_shed_the_address_or_the_card(self):
        for fingerprint in ("fpA", "fpB", "fpC", "fpD"):
            self.fail(fingerprint=fingerprint)
        second = User.objects.create_user(email="other@example.com", password="x")
        with self.assertRaises(guard.CardTestingBlocked):
            guard.check(second, self.ip, second.email)

    @override_settings(**{**SETTINGS, "CARD_GUARD_FRESH_ACCOUNT_MINUTES": 15})
    def test_an_account_made_a_moment_ago_starts_one_rung_up(self):
        fresh = User.objects.create_user(email="fresh@example.com", password="x")
        guard.record_failure(fresh, "198.51.100.4", fresh.email)
        with self.assertRaises(guard.CardTestingBlocked):
            guard.check(fresh, "198.51.100.4", fresh.email)

    # ---- email ------------------------------------------------------------
    def test_a_throwaway_inbox_is_refused_before_anything_fails(self):
        with self.assertRaises(guard.CardTestingBlocked):
            guard.check(None, "198.51.100.5", "someone@mailinator.com")

    def test_a_real_inbox_is_not(self):
        guard.check(None, "198.51.100.6", "someone@gmail.com")

    @override_settings(**{**SETTINGS, "CARD_GUARD_BLOCK_DISPOSABLE_EMAIL": False})
    def test_the_throwaway_rule_can_be_softened_without_a_deploy(self):
        guard.check(None, "198.51.100.7", "someone@mailinator.com")

    # ---- the off switch ---------------------------------------------------
    @override_settings(**{**SETTINGS, "CARD_GUARD_ENABLED": False})
    def test_everything_is_inert_when_switched_off(self):
        for fingerprint in ("fpA", "fpB", "fpC", "fpD"):
            self.fail(fingerprint=fingerprint)
        guard.check(self.user, self.ip, self.user.email)


@override_settings(**SETTINGS)
class EvasionSeenInProductionTests(TestCase):
    """Three holes the first day of real traffic walked straight through.

    Within a day of the app going live, four accounts signed up and opened
    several small card checkouts each within minutes. None of them paid, so
    nothing was lost, and none of them was slowed down either -- these are the
    reasons why.
    """

    def setUp(self):
        cache.clear()

    def test_gmail_dots_and_plus_addressing_are_one_inbox(self):
        # `d.a.w.di2153azdin@gmail.com` is a real address from the access log.
        # Gmail ignores dots, so it and its undotted twin reach the same person,
        # and counted literally each spelling is a fresh identity with a clean
        # record -- an unbounded supply of them from one mailbox.
        canonical = guard.canonical_email("dawdi2153azdin@gmail.com")
        for spelling in ("d.a.w.di2153azdin@gmail.com",
                         "DAW.DI2153AZDIN@gmail.com",
                         "dawdi2153azdin+shop@gmail.com",
                         "d.a.w.di2153azdin@googlemail.com"):
            with self.subTest(spelling=spelling):
                self.assertEqual(guard.canonical_email(spelling), canonical)

    def test_a_dot_still_matters_where_the_provider_says_it_does(self):
        # Only Gmail is dot-blind. Collapsing them everywhere would merge two
        # strangers at Outlook into one identity and punish both.
        self.assertNotEqual(guard.canonical_email("first.last@outlook.com"),
                            guard.canonical_email("firstlast@outlook.com"))

    def test_failures_carry_across_gmail_spellings(self):
        user = User.objects.create_user(email="dawdi2153azdin@gmail.com", password="x")
        for _ in range(3):
            guard.record_failure(user, "", "d.a.w.di2153azdin@gmail.com")
        # A new account, a new address spelling, the same mailbox.
        other = User.objects.create_user(email="x@example.com", password="x")
        with self.assertRaises(guard.CardTestingBlocked):
            guard.check(other, "", "dawdi2153azdin+again@googlemail.com")

    def test_the_throwaway_domain_from_the_access_log_is_known(self):
        self.assertTrue(guard.email_is_disposable("bayupart@moimoi.re"))

    def test_several_unfinished_checkouts_are_refused(self):
        # Four sessions in ninety seconds, none completed. No decline has
        # happened yet so the ladder has nothing to count, and four requests is
        # under any sane rate limit -- but nobody buys the same $5 four times in
        # a minute and a half.
        guard.check_open_sessions(2)
        with self.assertRaises(guard.CardTestingBlocked):
            guard.check_open_sessions(3)

    @override_settings(**{**SETTINGS, "CARD_GUARD_MAX_OPEN_SESSIONS": 0})
    def test_the_open_session_cap_can_be_switched_off(self):
        guard.check_open_sessions(99)
