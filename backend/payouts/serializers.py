from rest_framework import serializers
from .models import Payout, LedgerEntry, Merchant


class MerchantSerializer(serializers.ModelSerializer):
    class Meta:
        model = Merchant
        fields = ['id', 'name', 'email', 'bank_account_id', 'created_at']


class LedgerEntrySerializer(serializers.ModelSerializer):
    class Meta:
        model = LedgerEntry
        fields = ['id', 'entry_type', 'amount_paise', 'description',
                  'reference_id', 'created_at']


class PayoutSerializer(serializers.ModelSerializer):
    class Meta:
        model = Payout
        fields = [
            'id', 'merchant', 'amount_paise', 'bank_account_id',
            'status', 'idempotency_key', 'failure_reason',
            'attempt_count', 'created_at', 'updated_at', 'processed_at',
        ]
        read_only_fields = fields


class CreatePayoutSerializer(serializers.Serializer):
    amount_paise = serializers.IntegerField(min_value=100)  # minimum 1 rupee
    bank_account_id = serializers.CharField(max_length=100)

    def validate_amount_paise(self, value):
        if value <= 0:
            raise serializers.ValidationError("Amount must be positive.")
        return value