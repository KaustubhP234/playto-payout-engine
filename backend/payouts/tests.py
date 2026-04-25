import uuid
import threading
from django.test import TestCase, TransactionTestCase
from django.db import transaction

from .models import Merchant, LedgerEntry, Payout, IdempotencyKey
from .services import create_payout, InsufficientBalanceError


def make_merchant(name='Test Merchant', email=None, balance_paise=0):
    """Helper: create a merchant and optionally seed a credit balance."""
    email = email or f"{uuid.uuid4().hex[:8]}@test.com"
    merchant = Merchant.objects.create(
        name=name,
        email=email,
        bank_account_id=f"BANK_{uuid.uuid4().hex[:8]}",
    )
    if balance_paise > 0:
        LedgerEntry.objects.create(
            merchant=merchant,
            entry_type=LedgerEntry.CREDIT,
            amount_paise=balance_paise,
            description='Test credit',
        )
    return merchant


# =============================================================================
# IDEMPOTENCY TESTS
# =============================================================================

class IdempotencyTest(TestCase):
    """
    Verifies that the same Idempotency-Key always returns the same payout
    and never creates duplicate records.
    """

    def setUp(self):
        self.merchant = make_merchant(balance_paise=500000)  # ₹5000
        self.idempotency_key = str(uuid.uuid4())

    def test_same_key_returns_same_payout(self):
        """Two calls with the same key must return the exact same payout ID."""
        payout_1, created_1 = create_payout(
            merchant=self.merchant,
            amount_paise=100000,
            bank_account_id='BANK_TEST_001',
            idempotency_key=self.idempotency_key,
        )
        payout_2, created_2 = create_payout(
            merchant=self.merchant,
            amount_paise=100000,
            bank_account_id='BANK_TEST_001',
            idempotency_key=self.idempotency_key,
        )

        self.assertEqual(payout_1.id, payout_2.id,
                         "Same idempotency key must return same payout ID")
        self.assertTrue(created_1, "First call must be a new creation")
        self.assertFalse(created_2, "Second call must be a replay, not a new creation")

    def test_same_key_does_not_create_duplicate_payout(self):
        """Only one Payout row must exist after two calls with the same key."""
        create_payout(
            merchant=self.merchant,
            amount_paise=100000,
            bank_account_id='BANK_TEST_001',
            idempotency_key=self.idempotency_key,
        )
        create_payout(
            merchant=self.merchant,
            amount_paise=100000,
            bank_account_id='BANK_TEST_001',
            idempotency_key=self.idempotency_key,
        )

        payout_count = Payout.objects.filter(merchant=self.merchant).count()
        self.assertEqual(payout_count, 1,
                         "Exactly one payout must exist after duplicate requests")

    def test_different_keys_create_separate_payouts(self):
        """Two different idempotency keys must produce two separate payouts."""
        payout_1, _ = create_payout(
            merchant=self.merchant,
            amount_paise=100000,
            bank_account_id='BANK_TEST_001',
            idempotency_key=str(uuid.uuid4()),
        )
        payout_2, _ = create_payout(
            merchant=self.merchant,
            amount_paise=100000,
            bank_account_id='BANK_TEST_001',
            idempotency_key=str(uuid.uuid4()),
        )

        self.assertNotEqual(payout_1.id, payout_2.id,
                            "Different keys must produce different payouts")
        self.assertEqual(Payout.objects.filter(merchant=self.merchant).count(), 2)

    def test_key_scoped_per_merchant(self):
        """The same key string used by two different merchants must not collide."""
        merchant_2 = make_merchant(
            name='Merchant 2',
            balance_paise=500000
        )
        shared_key = str(uuid.uuid4())

        payout_1, created_1 = create_payout(
            merchant=self.merchant,
            amount_paise=100000,
            bank_account_id='BANK_A',
            idempotency_key=shared_key,
        )
        payout_2, created_2 = create_payout(
            merchant=merchant_2,
            amount_paise=100000,
            bank_account_id='BANK_B',
            idempotency_key=shared_key,
        )

        self.assertNotEqual(payout_1.id, payout_2.id,
                            "Same key for different merchants must create separate payouts")
        self.assertTrue(created_1)
        self.assertTrue(created_2)


# =============================================================================
# CONCURRENCY TESTS
# =============================================================================

class ConcurrencyTest(TransactionTestCase):
    """
    Uses TransactionTestCase (not TestCase) because select_for_update
    requires real committed transactions across threads.
    TestCase wraps everything in one transaction, which would deadlock.
    """

    def setUp(self):
        self.merchant = make_merchant(balance_paise=10000)  # ₹100 exactly

    def test_two_concurrent_payouts_one_must_fail(self):
        """
        Merchant has ₹100 (10000 paise).
        Two concurrent requests for ₹60 (6000 paise) each.
        Exactly one must succeed, the other must raise InsufficientBalanceError.
        Total held must not exceed available balance.
        """
        results = []
        errors = []

        def attempt_payout():
            try:
                payout, created = create_payout(
                    merchant=self.merchant,
                    amount_paise=6000,
                    bank_account_id='BANK_CONCURRENT_TEST',
                    idempotency_key=str(uuid.uuid4()),
                )
                results.append(payout)
            except InsufficientBalanceError as e:
                errors.append(e)

        t1 = threading.Thread(target=attempt_payout)
        t2 = threading.Thread(target=attempt_payout)

        t1.start()
        t2.start()
        t1.join()
        t2.join()

        total = len(results) + len(errors)
        self.assertEqual(total, 2, "Both threads must complete (success or error)")

        self.assertEqual(len(results), 1,
                         "Exactly ONE payout must succeed")
        self.assertEqual(len(errors), 1,
                         "Exactly ONE payout must be rejected")

        # Verify balance integrity
        self.merchant.refresh_from_db()
        balance = self.merchant.get_balance()
        self.assertGreaterEqual(
            balance['available_paise'], 0,
            "Available balance must never go negative"
        )
        self.assertLessEqual(
            balance['held_paise'], 10000,
            "Held balance must not exceed total credits"
        )

    def test_balance_never_goes_negative(self):
        """
        Fire 5 concurrent payout requests all larger than the balance.
        None should succeed — balance must stay at 10000.
        """
        errors = []
        results = []

        def attempt_payout():
            try:
                payout, _ = create_payout(
                    merchant=self.merchant,
                    amount_paise=8000,  # each request wants ₹80
                    bank_account_id='BANK_OVERDRAW_TEST',
                    idempotency_key=str(uuid.uuid4()),
                )
                results.append(payout)
            except InsufficientBalanceError as e:
                errors.append(e)

        threads = [threading.Thread(target=attempt_payout) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # Only 1 can succeed (10000 paise / 8000 paise = 1)
        self.assertLessEqual(len(results), 1,
                             "At most one 8000p payout can fit in a 10000p balance")

        balance = self.merchant.get_balance()
        self.assertGreaterEqual(balance['available_paise'], 0,
                                "Balance must never be negative")


# =============================================================================
# STATE MACHINE TESTS
# =============================================================================

class StateMachineTest(TestCase):
    """Verifies invalid transitions are blocked at the model layer."""

    def setUp(self):
        self.merchant = make_merchant(balance_paise=500000)

    def _make_payout(self, status=Payout.PENDING):
        p = Payout.objects.create(
            merchant=self.merchant,
            amount_paise=10000,
            bank_account_id='BANK_SM_TEST',
            idempotency_key=str(uuid.uuid4()),
            status=status,
        )
        return p

    def test_valid_transition_pending_to_processing(self):
        p = self._make_payout(Payout.PENDING)
        p.transition_to(Payout.PROCESSING)
        self.assertEqual(p.status, Payout.PROCESSING)

    def test_valid_transition_processing_to_completed(self):
        p = self._make_payout(Payout.PROCESSING)
        p.transition_to(Payout.COMPLETED)
        self.assertEqual(p.status, Payout.COMPLETED)

    def test_valid_transition_processing_to_failed(self):
        p = self._make_payout(Payout.PROCESSING)
        p.transition_to(Payout.FAILED)
        self.assertEqual(p.status, Payout.FAILED)

    def test_invalid_completed_to_pending(self):
        p = self._make_payout(Payout.COMPLETED)
        with self.assertRaises(ValueError):
            p.transition_to(Payout.PENDING)

    def test_invalid_failed_to_completed(self):
        p = self._make_payout(Payout.FAILED)
        with self.assertRaises(ValueError):
            p.transition_to(Payout.COMPLETED)

    def test_invalid_pending_to_completed(self):
        """Cannot skip processing."""
        p = self._make_payout(Payout.PENDING)
        with self.assertRaises(ValueError):
            p.transition_to(Payout.COMPLETED)

    def test_invalid_completed_to_failed(self):
        p = self._make_payout(Payout.COMPLETED)
        with self.assertRaises(ValueError):
            p.transition_to(Payout.FAILED)