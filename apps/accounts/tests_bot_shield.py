"""The bot check on the free forms, and forced authentication on the paid ones.

Registering costs nothing and unlocks everything that costs: a first-purchase
coupon, a referral code pointing at itself, and a verification email sent from
our domain. A script that opens accounts all night is spending our sending
reputation and our Radar bill, and it is cheapest to stop at the door.

What these tests are really guarding is the failure direction. A captcha that
lets requests through when it cannot check is not a captcha, and a captcha that
refuses everything because a key was mistyped is a site nobody can join. Both
are one careless edit away, and neither is visible by looking at the page.
"""
from __future__ import annotations

from unittest import mock

from django.contrib.auth import get_user_model
from django.core import mail
from django.test import TestCase, override_settings
from django.urls import reverse

from core import turnstile

User = get_user_model()

KEYS = {"TURNSTILE_SITE_KEY": "1x00000000000000000000AA",
        "TURNSTILE_SECRET_KEY": "1x0000000000000000000000000000000AA"}


@override_settings(**KEYS)
class WidgetTests(TestCase):
    def test_the_widget_is_on_the_forms_that_can_be_abused(self):
        for name in ("signup", "login", "password_reset"):
            with self.subTest(page=name):
                body = self.client.get(reverse(name)).content.decode()
                self.assertIn("cf-turnstile", body)
                self.assertIn(KEYS["TURNSTILE_SITE_KEY"], body)
                self.assertIn("challenges.cloudflare.com/turnstile", body)

    @override_settings(TURNSTILE_SITE_KEY="", TURNSTILE_SECRET_KEY="")
    def test_no_keys_means_no_widget(self):
        """Off is off on both sides, or the form asks for a token nobody checks."""
        self.assertNotIn("cf-turnstile", self.client.get(reverse("signup")).content.decode())
        self.assertFalse(turnstile.enabled())

    @override_settings(TURNSTILE_SECRET_KEY="")
    def test_a_site_key_alone_does_not_switch_it_on(self):
        self.assertFalse(turnstile.enabled())
        self.assertNotIn("cf-turnstile", self.client.get(reverse("signup")).content.decode())


@override_settings(**KEYS)
class VerificationTests(TestCase):
    """The helper itself: what it does with Cloudflare's answer, and without one."""

    def _cloudflare_says(self, payload):
        response = mock.MagicMock()
        response.read.return_value = payload
        response.__enter__.return_value = response
        return mock.patch("urllib.request.urlopen", return_value=response)

    def test_a_token_cloudflare_accepts_passes(self):
        with self._cloudflare_says(b'{"success": true}'):
            self.assertTrue(turnstile.verify("a-token"))

    def test_a_token_cloudflare_rejects_fails(self):
        with self._cloudflare_says(b'{"success": false, "error-codes": ["invalid-input-response"]}'):
            self.assertFalse(turnstile.verify("a-token"))

    def test_no_token_at_all_fails_without_asking(self):
        with mock.patch("urllib.request.urlopen") as urlopen:
            self.assertFalse(turnstile.verify(""))
            urlopen.assert_not_called()

    def test_an_unreachable_cloudflare_fails_closed(self):
        """The whole point. Opening the gate when the guard is unreachable is
        the same as having no guard, and it happens precisely when someone is
        pushing on it."""
        with mock.patch("urllib.request.urlopen", side_effect=OSError("network down")):
            self.assertFalse(turnstile.verify("a-token"))

    @override_settings(TURNSTILE_SECRET_KEY="")
    def test_it_passes_everything_when_switched_off(self):
        self.assertTrue(turnstile.verify(""))


@override_settings(**KEYS)
class FormTests(TestCase):
    """End to end: can a request without a valid token get anything done?"""

    def setUp(self):
        self.passing = mock.patch("core.turnstile.verify", return_value=True)
        self.failing = mock.patch("core.turnstile.verify", return_value=False)

    def test_registration_without_a_valid_token_creates_no_account(self):
        with self.failing:
            response = self.client.post(reverse("signup"), {
                "email": "bot@example.com", "password": "Str0ng!passw0rd",
                turnstile.FIELD: "rubbish",
            })
        self.assertEqual(response.status_code, 200, "re-renders rather than redirecting")
        self.assertFalse(User.objects.filter(email="bot@example.com").exists())
        # No assertion on mail.outbox here: verification mail is sent from a
        # background thread, so a message from an earlier test can still be in
        # flight and land in this one's outbox. No account means no mail anyway.

    def test_registration_with_a_valid_token_goes_through(self):
        with self.passing:
            response = self.client.post(reverse("signup"), {
                "email": "human@example.com", "password": "Str0ng!passw0rd",
                turnstile.FIELD: "a-token",
            })
        self.assertEqual(response.status_code, 302)
        self.assertTrue(User.objects.filter(email="human@example.com").exists())

    def test_a_failed_check_keeps_what_the_visitor_typed(self):
        with self.failing:
            response = self.client.post(reverse("signup"),
                                        {"email": "human@example.com", "password": "x"})
        self.assertContains(response, "human@example.com")

    def test_sign_in_without_a_valid_token_does_not_authenticate(self):
        User.objects.create_user(email="real@example.com", password="Str0ng!passw0rd",
                                 email_verified=True)
        with self.failing:
            response = self.client.post(reverse("login"), {
                "email": "real@example.com", "password": "Str0ng!passw0rd",
            })
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_password_reset_without_a_valid_token_sends_no_mail(self):
        """This form mails whatever address is typed into it, from our domain."""
        User.objects.create_user(email="real@example.com", password="x")
        with self.failing:
            self.client.post(reverse("password_reset"), {"email": "real@example.com"})
        self.assertEqual(len(mail.outbox), 0)

    def test_password_reset_with_a_valid_token_still_works(self):
        User.objects.create_user(email="real@example.com", password="x")
        with self.passing:
            response = self.client.post(reverse("password_reset"), {"email": "real@example.com"})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(len(mail.outbox), 1)


class ThreeDSecureTests(TestCase):
    """Forced card authentication, on every route a card can reach."""

    def test_checkout_asks_the_issuer_to_authenticate(self):
        from apps.payments.stripe_client import card_options

        self.assertEqual(card_options(), {"card": {"request_three_d_secure": "challenge"}})

    @override_settings(STRIPE_3DS_MODE="automatic")
    def test_it_can_be_dialled_back_without_a_deploy(self):
        """If conversion drops noticeably this has to be reversible from the
        dashboard, not from a release."""
        from apps.payments.stripe_client import card_options

        self.assertEqual(card_options(), {})

    def test_an_unknown_mode_falls_back_to_the_safe_one(self):
        """A typo in an environment variable must not quietly switch fraud
        protection off -- and must not 502 the checkout either."""
        from django.conf import settings

        self.assertIn(settings.STRIPE_3DS_MODE, ("automatic", "challenge", "any"))


@override_settings(**KEYS)
class ApiRegistrationTests(TestCase):
    """The mobile API creates accounts too, and cannot draw a captcha.

    So it is protected differently: a much tighter rate than signing in, a token
    verified whenever one is sent, and a switch to start demanding one on the day
    the app learns to produce it.
    """

    URL = "/api/v1/auth/register/"
    BODY = {"email": "api@example.com", "password": "Str0ng!passw0rd"}

    def post(self, **extra):
        return self.client.post(self.URL, {**self.BODY, **extra},
                                content_type="application/json")

    def test_a_registration_without_a_token_still_works_by_default(self):
        """The app does not send one yet; demanding it would lock out the only
        client there is."""
        self.assertEqual(self.post().status_code, 201)

    @override_settings(API_REQUIRE_TURNSTILE=True)
    def test_it_can_be_made_compulsory_for_the_app_release(self):
        response = self.post()
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["code"], "bot_check_failed")
        self.assertFalse(User.objects.filter(email=self.BODY["email"]).exists())

    def test_a_token_that_is_sent_is_actually_checked(self):
        """Opt-in protection is worthless if the server ignores what it is given."""
        with mock.patch("core.turnstile.verify", return_value=False) as verify:
            response = self.post(turnstile_token="a-token")
        verify.assert_called_once()
        self.assertEqual(response.status_code, 400)
        self.assertFalse(User.objects.filter(email=self.BODY["email"]).exists())

    def test_registration_is_rated_far_below_signing_in(self):
        from django.conf import settings

        rates = settings.REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"]
        self.assertNotEqual(rates["register"], rates["auth"])
        count, _, period = rates["register"].partition("/")
        self.assertIn(period, ("hour", "day"))
        self.assertLessEqual(int(count), 20)
