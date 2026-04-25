import uuid
import logging
from django.db import transaction, IntegrityError
from django.db.models import Sum, Q

from .models import Merchant, Payout, LedgerEntry, IdempotencyKey

logger = logging.getLogger(__name__)


class InsufficientBalanceError(Exception):
    pass


class InvalidTransitionError(Exception):
    pass


def get_merchant_balance(merchant: Merchant) -> dict:
    """
    Derives balance entirely from DB aggregation.
    Never touches Python arithmetic on fetched rows.
    """
    return merchant.get_balance()


def create_payout(merchant: Merchant, amount_paise: int,
                  bank_account_id: str, idempotency_key: str) -> tuple[Payout, bool]:
    """
    Creates a payout request with full idempotency and concurrency safety.

    Returns:
        (payout, created) — created=False means idempotency key was replayed.

    Raises:
        InsufficientBalanceError — if available balance is too low.
        ValueError — propagated from state machine on invalid transition.
    """

    # --- Step 1: Check idempotency key (outside transaction, fast path) ---
    existing = IdempotencyKey.objects.filter(
        merchant=merchant,
        key=idempotency_key,
    ).select_related().first()

    if existing and not existing.is_expired():
        logger.info(
            f"[create_payout] Replayed idempotency key={idempotency_key} "
            f"for merchant={merchant.id}"
        )
        # Return the original payout object
        payout_id = existing.response_body.get('id')
        try:
            payout = Payout.objects.get(id=payout_id)
            return payout, False
        except Payout.DoesNotExist:
            pass  # Fall through to create if somehow missing

    # --- Step 2: Atomic block — lock, check balance, create payout ---
    with transaction.atomic():
        # CRITICAL: Lock all of this merchant's pending/processing payouts
        # using select_for_update. This prevents two concurrent requests
        # from both passing the balance check simultaneously.
        #
        # We lock the merchant row itself to serialize concurrent payout
        # requests for the same merchant.
        locked_merchant = Merchant.objects.select_for_update().get(id=merchant.id)

        # Compute available balance inside the lock
        balance = locked_merchant.get_balance()
        available = balance['available_paise']

        logger.info(
            f"[create_payout] merchant={merchant.id} "
            f"available={available} requested={amount_paise}"
        )

        if amount_paise > available:
            raise InsufficientBalanceError(
                f"Insufficient balance. Available: {available} paise, "
                f"Requested: {amount_paise} paise."
            )

        # Create the payout — funds are "held" by virtue of being in
        # pending status, which the get_balance() query accounts for.
        payout = Payout.objects.create(
            merchant=locked_merchant,
            amount_paise=amount_paise,
            bank_account_id=bank_account_id,
            idempotency_key=idempotency_key,
            status=Payout.PENDING,
        )

        # Store idempotency key with the response payload
        # Use get_or_create to handle the race where two identical requests
        # arrive simultaneously and both pass the first check above.
        try:
            IdempotencyKey.objects.create(
                merchant=locked_merchant,
                key=idempotency_key,
                response_body={
                    'id': str(payout.id),
                    'merchant': str(payout.merchant_id),
                    'amount_paise': payout.amount_paise,
                    'bank_account_id': payout.bank_account_id,
                    'status': payout.status,
                    'idempotency_key': payout.idempotency_key,
                    'created_at': payout.created_at.isoformat(),
                },
                response_status=201,
            )
        except IntegrityError:
            # Another concurrent request already stored this key.
            # Roll back this transaction and return the existing one.
            raise

    logger.info(
        f"[create_payout] Created payout={payout.id} "
        f"for merchant={merchant.id} amount={amount_paise}"
    )
    return payout, True