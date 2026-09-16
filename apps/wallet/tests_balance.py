"""Store credit: what gets added, and what can be spent.

Two questions, and both of them are about money that is not ours.

Crediting has to equal what arrived. Crypto is the awkward one -- the customer
pays in a coin whose rate moves between the quote and the confirmation, so the
amount that lands is almost never the amount invoiced. Over is the customer's
money and has to be credited; under must not be treated as paid.

Spending has to be impossible without the balance to cover it. The ledger is the
record, so a spend that slips past the check is not just a free plan, it is a
wallet whose rows no longer add up to its balance.

The on-commit dance in these tests is not ceremony: settle_payment defers the
credit to commit, so without captureOnCommitCallbacks the wallet would stay at
zero and every assertion here would be testing nothing.
"""
from __future__ import annotations

from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings

from apps.payments.models import Payment
from apps.payments.services import process_nowpayments_ipn, settle_stripe_session
from apps.wallet.models import BalanceTopUp, InsufficientBalance, Wallet, WalletTransaction
from apps.wallet.services import credit_topup

User = get_user_model()
D = Decimal


@override_settings(ADMIN_NOTIFY_EMAILS=[], WALLET_BONUS_TIERS="25:2.00")
class TopUpBase(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(email="wallet@example.com", password="x")
        self.topup = BalanceTopUp.objects.create(
            user=self.user, amount_usd=D("25.00"), bonus_usd=D("2.00"))
        self.payment = Payment.objects.create(
            balance_topup=self.topup, user=self.user,
            provider=Payment.Provider.NOWPAYMENTS, amount_usd=D("25.00"),
            status=Payment.Status.WAITING,
        )

    def ipn(self, **fields):
        payload = {"order_id": str(self.payment.id), "payment_id": "np_1",
                   "payment_status": "finished", "pay_currency": "usdttrc20"}
        payload.update(fields)
        with self.captureOnCommitCallbacks(execute=True):
            process_nowpayments_ipn(payload)
        self.topup.refresh_from_db()
        self.payment.refresh_from_db()

    def balance(self) -> Decimal:
        return Wallet.for_user(self.user).balance_usd

    def ledger(self) -> Decimal:
        return sum((t.amount_usd for t in Wallet.for_user(self.user).transactions.all()),
                   D("0.00"))


class CryptoCreditTests(TopUpBase):
    def test_paying_the_invoice_credits_the_invoice_plus_the_bonus(self):
        self.ipn(actually_paid_at_fiat="25.00")
        self.assertEqual(self.topup.status, BalanceTopUp.Status.CREDITED)
        self.assertEqual(self.balance(), D("27.00"))
        self.assertEqual(self.ledger(), D("27.00"))

    def test_overpaying_credits_what_actually_arrived(self):
        """The rate moved, or the wallet rounded up. That difference is theirs."""
        self.ipn(actually_paid_at_fiat="27.40")
        self.assertEqual(self.topup.received_usd, D("27.40"))
        self.assertEqual(self.balance(), D("29.40"), "invoice would have been 25 + 2")

    def test_underpaying_credits_nothing_at_all(self):
        self.ipn(actually_paid_at_fiat="19.00")
        self.assertEqual(self.payment.status, Payment.Status.PARTIAL)
        self.assertFalse(self.payment.settled)
        self.assertNotEqual(self.topup.status, BalanceTopUp.Status.CREDITED)
        self.assertEqual(self.balance(), D("0.00"))

    def test_an_amount_we_cannot_work_out_is_not_treated_as_paid(self):
        """No fiat figure and no way to derive one. Silence is not payment."""
        self.ipn(actually_paid="0", pay_amount="0")
        self.assertEqual(self.payment.status, Payment.Status.PARTIAL)
        self.assertEqual(self.balance(), D("0.00"))

    def test_the_amount_is_derived_from_the_coin_when_no_fiat_figure_is_given(self):
        """Half the coin asked for is half the money, whatever the coin is."""
        self.ipn(pay_amount="100", actually_paid="50")
        self.assertEqual(self.payment.paid_amount_usd, D("12.50"))
        self.assertEqual(self.balance(), D("0.00"), "half an invoice buys nothing")

    def test_a_repeated_notification_credits_once(self):
        self.ipn(actually_paid_at_fiat="25.00")
        self.ipn(actually_paid_at_fiat="25.00")
        self.ipn(actually_paid_at_fiat="25.00")
        self.assertEqual(self.balance(), D("27.00"))
        self.assertEqual(
            WalletTransaction.objects.filter(balance_topup=self.topup).count(), 2,
            "one row for the money, one for the bonus, however many times it fires")

    def test_confirming_then_finished_credits_once(self):
        self.ipn(payment_status="confirming", actually_paid_at_fiat="25.00")
        self.assertEqual(self.balance(), D("0.00"), "not money until it is confirmed")
        self.ipn(payment_status="finished", actually_paid_at_fiat="25.00")
        self.assertEqual(self.balance(), D("27.00"))

    def test_an_expired_invoice_credits_nothing(self):
        self.ipn(payment_status="expired")
        self.assertEqual(self.balance(), D("0.00"))
        self.assertEqual(self.payment.status, Payment.Status.EXPIRED)


class CardCreditTests(TopUpBase):
    def setUp(self):
        super().setUp()
        self.payment.provider = Payment.Provider.STRIPE
        self.payment.save(update_fields=["provider"])

    def session(self, cents):
        with self.captureOnCommitCallbacks(execute=True):
            settle_stripe_session({
                "id": "cs_test_1", "client_reference_id": str(self.payment.id),
                "payment_intent": "pi_test_1", "payment_status": "paid",
                "amount_total": cents,
            })
        self.topup.refresh_from_db()
        self.payment.refresh_from_db()

    def test_the_captured_amount_is_what_gets_credited(self):
        self.session(2500)
        self.assertEqual(self.payment.paid_amount_usd, D("25.00"))
        self.assertEqual(self.balance(), D("27.00"))

    def test_a_card_that_captured_less_credits_nothing(self):
        """Should not happen with Stripe. If it ever does, it is not a top-up."""
        self.session(500)
        self.assertEqual(self.balance(), D("0.00"))
        self.assertEqual(self.payment.status, Payment.Status.PARTIAL)

    def test_the_webhook_and_the_return_page_together_credit_once(self):
        self.session(2500)
        self.session(2500)
        self.assertEqual(self.balance(), D("27.00"))

    def test_crediting_the_same_top_up_twice_is_a_no_op(self):
        """The last line of defence, in case a caller invents a third route in."""
        self.session(2500)
        credit_topup(self.topup)
        self.assertEqual(self.balance(), D("27.00"))


@override_settings(ADMIN_NOTIFY_EMAILS=[])
class SpendingTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(email="spender@example.com", password="x")
        Wallet.credit(self.user, D("10.00"), description="test credit")

    def balance(self):
        return Wallet.for_user(self.user).balance_usd

    def test_spending_more_than_the_balance_is_refused(self):
        with self.assertRaises(InsufficientBalance):
            Wallet.debit(self.user, D("10.01"), description="one cent too far")
        self.assertEqual(self.balance(), D("10.00"), "a refused spend moves nothing")

    def test_a_refused_spend_writes_no_ledger_row(self):
        before = WalletTransaction.objects.count()
        with self.assertRaises(InsufficientBalance):
            Wallet.debit(self.user, D("999.00"), description="nope")
        self.assertEqual(WalletTransaction.objects.count(), before)

    def test_spending_the_whole_balance_is_allowed_and_lands_on_zero(self):
        Wallet.debit(self.user, D("10.00"), description="all of it")
        self.assertEqual(self.balance(), D("0.00"))

    def test_an_empty_wallet_can_buy_nothing(self):
        Wallet.debit(self.user, D("10.00"), description="all of it")
        with self.assertRaises(InsufficientBalance):
            Wallet.debit(self.user, D("0.01"), description="not a cent left")

    def test_a_wallet_that_never_existed_can_buy_nothing(self):
        stranger = User.objects.create_user(email="broke@example.com", password="x")
        with self.assertRaises(InsufficientBalance):
            Wallet.debit(stranger, D("1.00"), description="no wallet, no credit")

    def test_the_balance_always_equals_the_sum_of_the_ledger(self):
        Wallet.debit(self.user, D("3.33"), description="a")
        Wallet.credit(self.user, D("1.11"), kind=WalletTransaction.Kind.REFUND, description="b")
        Wallet.debit(self.user, D("0.78"), description="c")
        wallet = Wallet.for_user(self.user)
        total = sum((t.amount_usd for t in wallet.transactions.all()), D("0.00"))
        self.assertEqual(wallet.balance_usd, total)
        self.assertEqual(wallet.balance_usd, D("7.00"))

    def test_every_row_records_the_balance_it_produced(self):
        """The ledger has to be readable a year later without replaying it."""
        Wallet.debit(self.user, D("2.50"), description="a")
        row = Wallet.for_user(self.user).transactions.first()
        self.assertEqual(row.balance_after_usd, D("7.50"))

    def test_a_zero_or_negative_movement_is_refused(self):
        for amount in (D("0.00"), D("-5.00")):
            with self.subTest(amount=amount):
                with self.assertRaises(ValueError):
                    Wallet.debit(self.user, amount, description="nonsense")


@override_settings(ADMIN_NOTIFY_EMAILS=[])
class PayWithBalanceTests(TestCase):
    """Paying for a plan out of credit -- the only spend path customers reach."""

    def setUp(self):
        from apps.orders.models import Order

        self.user = User.objects.create_user(email="payer@example.com", password="x")
        Wallet.credit(self.user, D("10.00"), description="test credit")
        self.order = Order.objects.create(
            user=self.user, email=self.user.email, plan_title="Italy 3 GB",
            subtotal_usd=D("6.99"), amount_usd=D("6.99"))

    def pay(self):
        from apps.wallet.services import pay_order_with_balance

        with self.captureOnCommitCallbacks(execute=True):
            return pay_order_with_balance(self.user, self.order)

    def test_paying_takes_exactly_the_order_total(self):
        self.pay()
        self.assertEqual(Wallet.for_user(self.user).balance_usd, D("3.01"))
        self.order.refresh_from_db()
        self.assertNotEqual(self.order.status, "pending",
                            "the money left, so the order has to have moved on")

    def test_the_same_order_cannot_be_paid_twice(self):
        from apps.wallet.models import AlreadyPaid

        self.pay()
        with self.assertRaises(AlreadyPaid):
            self.pay()
        self.assertEqual(Wallet.for_user(self.user).balance_usd, D("3.01"),
                         "a second attempt must not take the money again")

    def test_another_account_cannot_spend_its_balance_on_this_order(self):
        stranger = User.objects.create_user(email="stranger@example.com", password="x")
        Wallet.credit(stranger, D("50.00"), description="theirs")
        from apps.wallet.services import pay_order_with_balance

        with self.assertRaises(InsufficientBalance):
            pay_order_with_balance(stranger, self.order)
        self.assertEqual(Wallet.for_user(stranger).balance_usd, D("50.00"))

    def test_an_order_dearer_than_the_balance_is_refused_and_stays_unpaid(self):
        self.order.amount_usd = D("10.01")
        self.order.save(update_fields=["amount_usd"])
        with self.assertRaises(InsufficientBalance):
            self.pay()
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, "pending")
        self.assertEqual(Wallet.for_user(self.user).balance_usd, D("10.00"))
