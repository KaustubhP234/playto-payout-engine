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
    return merchant.get_balance()


def create_payout(merchant: Merchant, amount_paise: int,
                  bank_account_id: str, idempotency_key: str) -> tuple[Payout, bool]:
    """
    Returns (payout, created).
    Idempotency: always returns stored response_body, never re-serializes.
    """

    # --- Fast path: check idempotency key before acquiring any lock ---
    try:
        existing = IdempotencyKey.objects.get(merchant=merchant, key=idempotency_key)
        if not existing.is_expired():
            logger.info(f"[create_payout] Replayed key={idempotency_key}")
            payout_id = existing.response_body.get('id')
            try:
                payout = Payout.objects.get(id=payout_id)
                return payout, False
            except Payout.DoesNotExist:
                pass  # fall through to create
    except IdempotencyKey.DoesNotExist:
        pass  # new key — proceed normally

    # --- Atomic block: lock merchant, check balance, create payout ---
    try:
        with transaction.atomic():
            locked_merchant = Merchant.objects.select_for_update().get(id=merchant.id)

            # Re-check idempotency inside the lock to handle in-flight duplicates
            try:
                existing = IdempotencyKey.objects.get(
                    merchant=locked_merchant,
                    key=idempotency_key
                )
                if not existing.is_expired():
                    payout_id = existing.response_body.get('id')
                    try:
                        payout = Payout.objects.get(id=payout_id)
                        return payout, False
                    except Payout.DoesNotExist:
                        pass
            except IdempotencyKey.DoesNotExist:
                pass

            balance = locked_merchant.get_balance()
            available = balance['available_paise']

            if amount_paise > available:
                raise InsufficientBalanceError(
                    f"Insufficient balance. Available: {available} paise, "
                    f"Requested: {amount_paise} paise."
                )

            payout = Payout.objects.create(
                merchant=locked_merchant,
                amount_paise=amount_paise,
                bank_account_id=bank_account_id,
                idempotency_key=idempotency_key,
                status=Payout.PENDING,
            )

            # Store exact response body — this is what replays will return
            stored_response = {
                'id': str(payout.id),
                'merchant': str(payout.merchant_id),
                'amount_paise': payout.amount_paise,
                'bank_account_id': payout.bank_account_id,
                'status': payout.status,
                'idempotency_key': payout.idempotency_key,
                'failure_reason': payout.failure_reason,
                'attempt_count': payout.attempt_count,
                'created_at': payout.created_at.isoformat(),
                'updated_at': payout.updated_at.isoformat(),
                'processed_at': None,
            }

            IdempotencyKey.objects.create(
                merchant=locked_merchant,
                key=idempotency_key,
                response_body=stored_response,
                response_status=201,
            )

    except IntegrityError:
        # In-flight duplicate: another request stored the key just now
        # Retry the lookup to return the stored response
        try:
            existing = IdempotencyKey.objects.get(
                merchant=merchant,
                key=idempotency_key
            )
            payout_id = existing.response_body.get('id')
            payout = Payout.objects.get(id=payout_id)
            return payout, False
        except (IdempotencyKey.DoesNotExist, Payout.DoesNotExist):
            raise

    logger.info(f"[create_payout] Created payout={payout.id}")
    return payout, True