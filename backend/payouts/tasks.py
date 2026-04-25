import random
import logging
from celery import shared_task
from django.db import transaction
from django.utils import timezone

from .models import Payout, LedgerEntry

logger = logging.getLogger(__name__)

# Retry config
MAX_ATTEMPTS = 3
STUCK_THRESHOLD_SECONDS = 30


@shared_task(bind=True, max_retries=MAX_ATTEMPTS)
def process_payout(self, payout_id: str):
    """
    Main payout processor.
    Picks up a pending payout, moves it to processing, then simulates
    bank settlement: 70% success, 20% failure, 10% stuck.
    """
    logger.info(f"[process_payout] Starting task for payout_id={payout_id}")

    try:
        with transaction.atomic():
            # Lock the payout row for this task
            payout = Payout.objects.select_for_update().get(id=payout_id)

            # Guard: only process pending payouts
            if payout.status != Payout.PENDING:
                logger.warning(
                    f"[process_payout] Payout {payout_id} is in status "
                    f"'{payout.status}', skipping."
                )
                return

            # Transition: pending → processing
            payout.transition_to(Payout.PROCESSING)
            payout.attempt_count += 1
            payout.save(update_fields=['status', 'attempt_count', 'updated_at'])

    except Payout.DoesNotExist:
        logger.error(f"[process_payout] Payout {payout_id} not found.")
        return

    # --- Simulate bank response (outside the first transaction) ---
    outcome = _simulate_bank_response()
    logger.info(f"[process_payout] Payout {payout_id} outcome={outcome}")

    if outcome == 'success':
        _complete_payout(payout_id)
    elif outcome == 'failure':
        _fail_payout(payout_id, reason="Bank declined the transfer.")
    else:
        # 'stuck' — task ends without updating status.
        # retry_stuck_payouts periodic task will detect and retry this.
        logger.warning(
            f"[process_payout] Payout {payout_id} is stuck in processing."
        )


def _simulate_bank_response() -> str:
    roll = random.random()
    if roll < 0.70:
        return 'success'
    elif roll < 0.90:
        return 'failure'
    else:
        return 'stuck'


def _complete_payout(payout_id: str):
    """
    Marks payout completed and writes the debit ledger entry.
    Atomic — both happen or neither happens.
    """
    with transaction.atomic():
        payout = Payout.objects.select_for_update().get(id=payout_id)

        if payout.status != Payout.PROCESSING:
            logger.warning(
                f"[_complete_payout] Payout {payout_id} not in processing, "
                f"current status={payout.status}"
            )
            return

        payout.transition_to(Payout.COMPLETED)
        payout.processed_at = timezone.now()
        payout.save(update_fields=['status', 'processed_at', 'updated_at'])

        # Write the debit entry — this is what actually moves money out
        LedgerEntry.objects.create(
            merchant=payout.merchant,
            entry_type=LedgerEntry.DEBIT,
            amount_paise=payout.amount_paise,
            description=f"Payout to bank account {payout.bank_account_id}",
            reference_id=str(payout.id),
        )

    logger.info(f"[_complete_payout] Payout {payout_id} completed successfully.")


def _fail_payout(payout_id: str, reason: str):
    """
    Marks payout failed.
    Held funds are released automatically because:
    - Balance = credits - debits
    - Held = SUM of pending/processing payouts
    - Once status moves to failed, this payout no longer counts in held
    No separate refund ledger entry needed — the hold simply lifts.
    This is atomic.
    """
    with transaction.atomic():
        payout = Payout.objects.select_for_update().get(id=payout_id)

        if payout.status != Payout.PROCESSING:
            logger.warning(
                f"[_fail_payout] Payout {payout_id} not in processing, "
                f"current status={payout.status}"
            )
            return

        payout.transition_to(Payout.FAILED)
        payout.failure_reason = reason
        payout.processed_at = timezone.now()
        payout.save(
            update_fields=['status', 'failure_reason', 'processed_at', 'updated_at']
        )

    logger.info(f"[_fail_payout] Payout {payout_id} failed. Reason: {reason}")


@shared_task
def retry_stuck_payouts():
    """
    Periodic task: detects payouts stuck in 'processing' for > 30 seconds.
    Retries up to MAX_ATTEMPTS times with exponential backoff.
    After max attempts → fail + release held funds.
    """
    cutoff = timezone.now() - timezone.timedelta(seconds=STUCK_THRESHOLD_SECONDS)

    stuck_payouts = Payout.objects.filter(
        status=Payout.PROCESSING,
        updated_at__lt=cutoff,
    )

    for payout in stuck_payouts:
        logger.warning(
            f"[retry_stuck_payouts] Payout {payout.id} stuck since "
            f"{payout.updated_at}. Attempt {payout.attempt_count}/{MAX_ATTEMPTS}"
        )

        if payout.attempt_count >= MAX_ATTEMPTS:
            # Exhausted retries — fail it and release the hold
            _fail_payout(
                str(payout.id),
                reason=f"Exhausted {MAX_ATTEMPTS} attempts. Marked failed by retry worker."
            )
        else:
            # Reset to pending so process_payout can pick it up again
            with transaction.atomic():
                p = Payout.objects.select_for_update().get(id=payout.id)
                if p.status == Payout.PROCESSING:
                    p.status = Payout.PENDING
                    p.save(update_fields=['status', 'updated_at'])

            # Exponential backoff: 2^attempt_count seconds
            countdown = 2 ** payout.attempt_count
            process_payout.apply_async(
                args=[str(payout.id)],
                countdown=countdown
            )
            logger.info(
                f"[retry_stuck_payouts] Retrying payout {payout.id} "
                f"in {countdown}s (attempt {payout.attempt_count + 1})"
            )