import uuid
from django.db import models
from django.db.models import Sum
from django.utils import timezone


class Merchant(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=255)
    email = models.EmailField(unique=True)
    bank_account_id = models.CharField(max_length=100)
    created_at = models.DateTimeField(auto_now_add=True)

    def get_balance(self):
        """
        Balance is ALWAYS derived from the ledger using DB aggregation.
        Never computed in Python from fetched rows.
        Returns a dict with available_paise and held_paise.
        """
        result = self.ledger_entries.aggregate(
            total_credits=Sum(
                'amount_paise',
                filter=models.Q(entry_type=LedgerEntry.CREDIT)
            ),
            total_debits=Sum(
                'amount_paise',
                filter=models.Q(entry_type=LedgerEntry.DEBIT)
            ),
        )
        total_credits = result['total_credits'] or 0
        total_debits = result['total_debits'] or 0

        held_paise = self.payouts.filter(
            status__in=[Payout.PENDING, Payout.PROCESSING]
        ).aggregate(
            held=Sum('amount_paise')
        )['held'] or 0

        net = total_credits - total_debits
        available = net - held_paise

        return {
            'available_paise': available,
            'held_paise': held_paise,
            'total_credits_paise': total_credits,
            'total_debits_paise': total_debits,
        }

    def __str__(self):
        return f"{self.name} ({self.email})"


class LedgerEntry(models.Model):
    CREDIT = 'credit'
    DEBIT = 'debit'
    ENTRY_TYPE_CHOICES = [
        (CREDIT, 'Credit'),
        (DEBIT, 'Debit'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    merchant = models.ForeignKey(
        Merchant,
        on_delete=models.PROTECT,
        related_name='ledger_entries'
    )
    entry_type = models.CharField(max_length=10, choices=ENTRY_TYPE_CHOICES)

    # CRITICAL: BigIntegerField only. Never FloatField or DecimalField.
    amount_paise = models.BigIntegerField()

    description = models.CharField(max_length=500)
    reference_id = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['merchant', 'entry_type']),
            models.Index(fields=['created_at']),
        ]

    def __str__(self):
        return f"{self.entry_type.upper()} {self.amount_paise}p — {self.merchant.name}"


class IdempotencyKey(models.Model):
    """
    Stores idempotency keys scoped per merchant.
    Prevents duplicate payout creation on retried requests.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    merchant = models.ForeignKey(
        Merchant,
        on_delete=models.CASCADE,
        related_name='idempotency_keys'
    )
    key = models.CharField(max_length=255)
    response_body = models.JSONField()
    response_status = models.IntegerField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        # A key is unique per merchant — not globally
        unique_together = ('merchant', 'key')
        indexes = [
            models.Index(fields=['merchant', 'key']),
        ]

    def is_expired(self):
        return (timezone.now() - self.created_at).total_seconds() > 86400  # 24 hours

    def __str__(self):
        return f"Key:{self.key} — {self.merchant.name}"


class Payout(models.Model):
    # --- State constants ---
    PENDING = 'pending'
    PROCESSING = 'processing'
    COMPLETED = 'completed'
    FAILED = 'failed'

    STATUS_CHOICES = [
        (PENDING, 'Pending'),
        (PROCESSING, 'Processing'),
        (COMPLETED, 'Completed'),
        (FAILED, 'Failed'),
    ]

    # Valid forward transitions only
    VALID_TRANSITIONS = {
        PENDING: [PROCESSING],
        PROCESSING: [COMPLETED, FAILED],
        COMPLETED: [],   # terminal — no transitions allowed
        FAILED: [],      # terminal — no transitions allowed
    }

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    merchant = models.ForeignKey(
        Merchant,
        on_delete=models.PROTECT,
        related_name='payouts'
    )

    # CRITICAL: BigIntegerField only
    amount_paise = models.BigIntegerField()

    bank_account_id = models.CharField(max_length=100)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=PENDING)
    idempotency_key = models.CharField(max_length=255)
    failure_reason = models.TextField(blank=True)
    attempt_count = models.IntegerField(default=0)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    processed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['merchant', 'status']),
            models.Index(fields=['status', 'updated_at']),
            models.Index(fields=['idempotency_key', 'merchant']),
        ]

    def transition_to(self, new_status):
        """
        Enforces the state machine at the model layer.
        Raises ValueError on illegal transitions.
        This is called inside atomic transactions — never outside.
        """
        allowed = self.VALID_TRANSITIONS.get(self.status, [])
        if new_status not in allowed:
            raise ValueError(
                f"Invalid transition: {self.status} → {new_status}. "
                f"Allowed from '{self.status}': {allowed}"
            )
        self.status = new_status

    def __str__(self):
        return f"Payout {self.id} | {self.amount_paise}p | {self.status}"