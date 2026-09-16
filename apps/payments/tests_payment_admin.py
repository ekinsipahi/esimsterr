"""The payments changelist, which has to open on every kind of payment.

A payment is for an order or for store credit, and the list column assumed the
first. One person buying balance was enough to make the page that lists payments
the page nobody could open -- and the payment you most want to look at is the one
that just went wrong.
"""
from __future__ import annotations

from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.orders.models import Order
from apps.payments.models import Payment
from apps.wallet.models import BalanceTopUp

User = get_user_model()


class PaymentAdminTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.staff = User.objects.create_superuser(email="admin@esimsterr.com", password="x")
        cls.customer = User.objects.create_user(email="buyer@example.com", password="x")

        order = Order.objects.create(
            user=cls.customer, email=cls.customer.email, plan_title="Spain 5 GB",
            subtotal_usd=Decimal("9.99"), amount_usd=Decimal("9.99"))
        Payment.objects.create(order=order, user=cls.customer,
                               provider=Payment.Provider.STRIPE, amount_usd=Decimal("9.99"))

        topup = BalanceTopUp.objects.create(user=cls.customer, amount_usd=Decimal("25.00"))
        Payment.objects.create(balance_topup=topup, user=cls.customer,
                               provider=Payment.Provider.NOWPAYMENTS, amount_usd=Decimal("25.00"))

    def setUp(self):
        self.client.force_login(self.staff)

    def test_the_changelist_opens_with_both_kinds_of_payment(self):
        response = self.client.get(reverse("admin:payments_payment_changelist"))
        self.assertEqual(response.status_code, 200)
        body = response.content.decode()
        self.assertIn("(balance)", body)

    def test_searching_finds_a_balance_payment_by_its_reference(self):
        ref = BalanceTopUp.objects.get().ref
        response = self.client.get(reverse("admin:payments_payment_changelist"), {"q": ref})
        self.assertEqual(response.status_code, 200)
        self.assertIn(ref, response.content.decode())
