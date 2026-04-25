# EXPLAINER.md — Playto Payout Engine

---

## 1. The Ledger

**Balance calculation query:**

```python
result = self.ledger_entries.aggregate(
    total_credits=Sum('amount_paise', filter=Q(entry_type=LedgerEntry.CREDIT)),
    total_debits=Sum('amount_paise',  filter=Q(entry_type=LedgerEntry.DEBIT)),
)
held_paise = self.payouts.filter(
    status__in=[Payout.PENDING, Payout.PROCESSING]
).aggregate(held=Sum('amount_paise'))['held'] or 0

available = (total_credits - total_debits) - held_paise
```

**Why modeled this way:**

Credits and debits are separate immutable `LedgerEntry` rows with an `entry_type` field.
Balance is never stored as a column — it is always derived from aggregation at query time.
This means there is no balance field to go out of sync, no update contention on a single row,
and a full audit trail of every money movement by design.

Held balance is derived from payouts in `pending` or `processing` state.
When a payout fails, its status moves to `failed` and it drops out of the held sum automatically —
no separate refund credit entry is needed, which eliminates a class of double-counting bugs.

---

## 2. The Lock

**Exact code that prevents concurrent overdraw:**

```python
with transaction.atomic():
    locked_merchant = Merchant.objects.select_for_update().get(id=merchant.id)
    balance = locked_merchant.get_balance()
    available = balance['available_paise']

    if amount_paise > available:
        raise InsufficientBalanceError(...)

    payout = Payout.objects.create(
        merchant=locked_merchant,
        amount_paise=amount_paise,
        status=Payout.PENDING,
        ...
    )
```

**Database primitive it relies on:**

`SELECT ... FOR UPDATE` — a PostgreSQL row-level exclusive lock.

When Thread 1 runs `select_for_update()` on the merchant row, PostgreSQL acquires an exclusive
lock on that row for the duration of the transaction. Thread 2's `select_for_update()` on the
same row will block at the database level until Thread 1's transaction commits or rolls back.

By the time Thread 2 is unblocked, the balance query it runs will reflect Thread 1's payout
already held — so if the balance is now insufficient, Thread 2 correctly raises
`InsufficientBalanceError`. This is guaranteed by the database, not by Python.

This eliminates the check-then-act race condition: there is no window between reading the
balance and creating the payout where another transaction can intervene.

---

## 3. The Idempotency

**How the system recognises a seen key:**

An `IdempotencyKey` model stores `(merchant, key)` as a `unique_together` constraint.
On every payout request, the service layer does a fast read outside the transaction first:

```python
existing = IdempotencyKey.objects.filter(
    merchant=merchant, key=idempotency_key
).first()

if existing and not existing.is_expired():
    payout = Payout.objects.get(id=existing.response_body['id'])
    return payout, False   # created=False signals a replay
```

If the key is new, the service proceeds into the atomic transaction, creates the payout,
then writes the `IdempotencyKey` row with the full response payload stored as JSON.

**What happens if the first request is in-flight when the second arrives:**

The fast read returns nothing (key not yet stored). Both requests enter the atomic transaction.
The `unique_together` constraint causes the second transaction's `IdempotencyKey.objects.create()`
to raise `IntegrityError`. This is caught explicitly:

```python
try:
    IdempotencyKey.objects.create(merchant=..., key=..., response_body=..., ...)
except IntegrityError:
    raise  # rolls back the transaction — no duplicate payout is committed
```

The second request's transaction rolls back entirely. The first payout is the only one committed.
Keys are scoped per merchant — the same UUID string from two different merchants does not collide.
Keys expire after 24 hours via `is_expired()` check.

---

## 4. The State Machine

**Where failed-to-completed is blocked:**

In `Payout.transition_to()` in `payouts/models.py`:

```python
VALID_TRANSITIONS = {
    'pending':    ['processing'],
    'processing': ['completed', 'failed'],
    'completed':  [],   # terminal
    'failed':     [],   # terminal
}

def transition_to(self, new_status):
    allowed = self.VALID_TRANSITIONS.get(self.status, [])
    if new_status not in allowed:
        raise ValueError(
            f"Invalid transition: {self.status} → {new_status}. "
            f"Allowed from '{self.status}': {allowed}"
        )
    self.status = new_status
```

`completed` and `failed` map to empty lists. Any call to `transition_to()` from either of
these states raises `ValueError` before any database write occurs. This is enforced at the
model layer, not in view or task code, so no code path can bypass it.

The state machine is always called inside `transaction.atomic()` in the task layer, so a
failed transition rolls back any partial writes in the same block.

---

## 5. The AI Audit

**What AI generated (wrong):**

When asked to write the failure refund logic, the AI produced:

```python
# AI version — WRONG
def _fail_payout(payout_id):
    with transaction.atomic():
        payout = Payout.objects.get(id=payout_id)   # no select_for_update
        payout.status = 'failed'                     # bypasses state machine
        payout.save()
        # Creates a credit ledger entry to "refund" held funds
        LedgerEntry.objects.create(
            merchant=payout.merchant,
            entry_type=LedgerEntry.CREDIT,
            amount_paise=payout.amount_paise,
            description='Refund for failed payout',
        )
```

**What was wrong:**

Two bugs:

1. No `select_for_update()` — a concurrent retry task could read the same payout simultaneously,
   both see `processing`, both try to fail it and both write a refund credit.
   This would create a phantom credit — money that never existed appearing in the balance.

2. The refund credit entry is architecturally wrong. Balance is derived as
   `SUM(credits) - SUM(debits) - SUM(held)`. When a payout moves to `failed`, it exits
   the `held` sum automatically. Writing an extra credit entry double-counts the funds —
   the merchant would see more balance than they ever received.

**What was replaced with:**

```python
# Correct version
def _fail_payout(payout_id, reason):
    with transaction.atomic():
        payout = Payout.objects.select_for_update().get(id=payout_id)
        if payout.status != Payout.PROCESSING:
            return  # idempotency guard — already handled
        payout.transition_to(Payout.FAILED)  # enforces state machine
        payout.failure_reason = reason
        payout.processed_at = timezone.now()
        payout.save(update_fields=['status', 'failure_reason', 'processed_at', 'updated_at'])
    # No refund entry — the held sum drops naturally when status leaves pending/processing
```