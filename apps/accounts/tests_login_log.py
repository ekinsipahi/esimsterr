"""Where each account was signed up and signed in from.

Two things are easy to get wrong here and neither shows on a page.

The first is coverage. The website opens a session and the app does not, so a
log hung off Django's ``user_logged_in`` signal silently covers half the
customers -- and it is the app half, the one that was invisible before, that
anybody looking for card testing wants to see. These tests sign in through both
surfaces and insist on a row either way.

The second is double counting. A view that records an event *and* fires the
signal logs the same sign-in twice, which does not look like a bug, it looks
like a person who signed in twice. So the counts here are exact.
"""
from __future__ import annotations

from unittest import mock

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from .models import LoginEvent

User = get_user_model()

# Both keys blank turns the bot check off rather than failing it, which is
# what core/turnstile.enabled() is for. Without this the forms below are
# refused by a captcha that has nothing to do with what is being tested.
NO_BOT_CHECK = {"TURNSTILE_SITE_KEY": "", "TURNSTILE_SECRET_KEY": "",
                "API_REQUIRE_TURNSTILE": False}

PASSWORD = "sufficiently-long-passphrase"
WEB_IP = "198.51.100.7"
APP_IP = "203.0.113.42"


@override_settings(**NO_BOT_CHECK)
class WebsiteTests(TestCase):
    def test_signing_up_records_where_from_even_though_nobody_is_logged_in(self):
        """Registration deliberately does not sign anyone in -- the address is
        unproven until the link is opened -- so the signal never fires and the
        sign-up has to be recorded by the view itself."""
        resp = self.client.post(
            reverse("signup"),
            {"email": "new@example.com", "password": PASSWORD},
            HTTP_CF_CONNECTING_IP=WEB_IP,
        )
        self.assertEqual(resp.status_code, 302)

        user = User.objects.get(email="new@example.com")
        event = LoginEvent.objects.get(user=user)
        self.assertEqual(event.event, LoginEvent.Event.SIGNUP)
        self.assertEqual(event.method, LoginEvent.Method.EMAIL)
        self.assertEqual(event.surface, "web")
        self.assertEqual(event.ip, WEB_IP)
        # The column on the account row was already filled in by the view; the
        # log must agree with it rather than inventing a second answer.
        self.assertEqual(user.signup_ip, WEB_IP)

    def test_signing_in_is_logged_once_and_moves_the_last_seen_address(self):
        user = User.objects.create_user(email="back@example.com", password=PASSWORD,
                                        email_verified=True)
        resp = self.client.post(
            reverse("login"),
            {"email": "back@example.com", "password": PASSWORD},
            HTTP_CF_CONNECTING_IP=WEB_IP,
        )
        self.assertEqual(resp.status_code, 302)

        events = LoginEvent.objects.filter(user=user)
        self.assertEqual(events.count(), 1, "one sign-in must not log two rows")
        self.assertEqual(events[0].event, LoginEvent.Event.LOGIN)
        self.assertEqual(events[0].method, LoginEvent.Method.EMAIL)
        user.refresh_from_db()
        self.assertEqual(user.last_login_ip, WEB_IP)

    def test_an_address_the_visitor_claimed_is_not_the_one_recorded(self):
        """The whole point of recording an address is that the person being
        looked at did not choose it.

        X-Forwarded-For is written by the caller. Cloudflare overwrites
        CF-Connecting-IP, which is why RealIPMiddleware trusts only that one.
        A sign-in log that believed the forged header would hand an attacker
        the ability to pin their sessions on any address they liked -- and it
        would read as evidence.
        """
        User.objects.create_user(email="liar@example.com", password=PASSWORD,
                                 email_verified=True)
        self.client.post(
            reverse("login"),
            {"email": "liar@example.com", "password": PASSWORD},
            HTTP_CF_CONNECTING_IP=WEB_IP,
            HTTP_X_FORWARDED_FOR="8.8.8.8, 10.0.0.1",
        )
        self.assertEqual(LoginEvent.objects.get().ip, WEB_IP)


@override_settings(**NO_BOT_CHECK)
class MobileAppTests(TestCase):
    """The app holds a JWT and never opens a session, so none of this is
    reachable from the signal the website relies on."""

    def test_app_sign_in_is_logged_against_the_app(self):
        user = User.objects.create_user(email="phone@example.com", password=PASSWORD,
                                        email_verified=True)
        resp = self.client.post(
            reverse("api_login"),
            {"email": "phone@example.com", "password": PASSWORD},
            HTTP_CF_CONNECTING_IP=APP_IP,
        )
        self.assertEqual(resp.status_code, 200)

        event = LoginEvent.objects.get(user=user)
        self.assertEqual(event.surface, "app")
        self.assertEqual(event.event, LoginEvent.Event.LOGIN)
        self.assertEqual(event.ip, APP_IP)
        user.refresh_from_db()
        self.assertEqual(user.last_login_ip, APP_IP)
        # Django only maintains last_login for session logins, so an account
        # used daily from the phone used to read as dormant.
        self.assertIsNotNone(user.last_login)

    def test_app_google_signup_records_the_address_it_came_from(self):
        """This path created accounts with an empty signup_ip, which meant the
        accounts worth looking at were the ones with nothing recorded."""
        with mock.patch("apps.api.views.user_from_google_token") as fake:
            def _create(token, signup_ip=None):
                return User.objects.create_user(
                    email="g@example.com", password=PASSWORD,
                    email_verified=True, signup_ip=signup_ip,
                ), True
            fake.side_effect = _create
            resp = self.client.post(reverse("api_google"), {"id_token": "x"},
                                    HTTP_CF_CONNECTING_IP=APP_IP)

        self.assertEqual(resp.status_code, 200)
        user = User.objects.get(email="g@example.com")
        self.assertEqual(user.signup_ip, APP_IP, "the IP must reach the account row")
        event = LoginEvent.objects.get(user=user)
        self.assertEqual(event.event, LoginEvent.Event.SIGNUP)
        self.assertEqual(event.method, LoginEvent.Method.GOOGLE)
        self.assertEqual(event.surface, "app")


@override_settings(**NO_BOT_CHECK)
class RingDetectionTests(TestCase):
    def test_one_address_finds_every_account_that_used_it(self):
        """The question an address is looked up to answer. Four accounts from
        one address within minutes is the shape launch day actually had."""
        for i in range(4):
            user = User.objects.create_user(email=f"ring{i}@example.com",
                                            password=PASSWORD, email_verified=True)
            self.client.post(reverse("login"),
                             {"email": user.email, "password": PASSWORD},
                             HTTP_CF_CONNECTING_IP=APP_IP)
            self.client.logout()

        self.assertEqual(
            LoginEvent.objects.filter(ip=APP_IP).values("user").distinct().count(), 4)


@override_settings(**NO_BOT_CHECK)
class FailureTests(TestCase):
    def test_a_broken_log_does_not_lock_anybody_out(self):
        """Somebody who cannot get into their account because an audit row
        failed to insert is worse than a gap in the log."""
        User.objects.create_user(email="resilient@example.com", password=PASSWORD,
                                 email_verified=True)
        with mock.patch("apps.accounts.login_log.LoginEvent.objects.create",
                        side_effect=RuntimeError("table is gone")):
            resp = self.client.post(reverse("login"),
                                    {"email": "resilient@example.com", "password": PASSWORD})
        self.assertEqual(resp.status_code, 302, "the sign-in must still succeed")
        self.assertEqual(LoginEvent.objects.count(), 0)


@override_settings(**NO_BOT_CHECK)
class DeletionTests(TestCase):
    def test_deleting_an_account_erases_its_addresses(self):
        """An IP is personal data and the orders already have theirs cleared on
        the same grounds. The fraud blocklist is separate and must survive --
        deleting an account cannot be a way to lift a ban."""
        from .deletion import delete_account

        user = User.objects.create_user(email="gone@example.com", password=PASSWORD,
                                        email_verified=True, signup_ip=WEB_IP)
        self.client.post(reverse("login"),
                         {"email": "gone@example.com", "password": PASSWORD},
                         HTTP_CF_CONNECTING_IP=WEB_IP)
        self.assertEqual(LoginEvent.objects.filter(user=user).count(), 1)

        report = delete_account(user)

        self.assertEqual(report.login_events_deleted, 1)
        self.assertEqual(LoginEvent.objects.filter(user=user).count(), 0)
        user.refresh_from_db()
        self.assertIsNone(user.signup_ip)
        self.assertIsNone(user.last_login_ip)


@override_settings(**NO_BOT_CHECK)
class AdminTests(TestCase):
    """The screens exist to be looked at, and an admin page that raises is a
    500 nobody sees until the morning they need it."""

    def setUp(self):
        self.staff = User.objects.create_superuser(email="ops@example.com",
                                                   password=PASSWORD)
        self.staff.email_verified = True
        self.staff.save(update_fields=["email_verified"])
        self.client.force_login(self.staff)
        self.subject = User.objects.create_user(email="looked-at@example.com",
                                                password=PASSWORD, email_verified=True,
                                                signup_ip=WEB_IP)

    def test_the_account_page_renders_with_no_history_recorded(self):
        """Every account that predates the log lands here first."""
        r = self.client.get(
            reverse("admin:accounts_user_change", args=[self.subject.pk]))
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "Nothing recorded")

    def test_the_account_page_shows_where_it_has_been_used_from(self):
        from .login_log import record_login

        record_login(self.subject, None, ip=APP_IP, surface="app")
        r = self.client.get(
            reverse("admin:accounts_user_change", args=[self.subject.pk]))
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, APP_IP)
        self.assertContains(r, "Card payments allowed")

    def test_a_blocked_account_says_so_on_its_own_page(self):
        """The blocklist is keyed by UUID, so this is where staff find out
        whether the person they are looking at is the one who was banned."""
        from payguard import permanently_block

        permanently_block(user=self.subject, email=self.subject.email,
                          reason="stripe decline_code=stolen_card")
        r = self.client.get(
            reverse("admin:accounts_user_change", args=[self.subject.pk]))
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "Blocked from card payments")
        self.assertContains(r, "stolen_card")

    def test_the_signin_list_and_the_blocklist_both_open(self):
        for name in ("admin:accounts_loginevent_changelist",
                     "admin:payguard_cardcooldown_changelist",
                     "admin:payguard_cardattempt_changelist"):
            with self.subTest(screen=name):
                self.assertEqual(self.client.get(reverse(name)).status_code, 200)

    def test_an_address_can_be_searched_for_across_accounts(self):
        """The query that turns one suspicious address into the list of
        accounts behind it."""
        from .login_log import record_login

        record_login(self.subject, None, ip=APP_IP)
        r = self.client.get(
            reverse("admin:accounts_loginevent_changelist") + f"?q={APP_IP}")
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "looked-at@example.com")
