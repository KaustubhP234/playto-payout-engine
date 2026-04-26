import logging
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from django.shortcuts import get_object_or_404

from .models import Merchant, Payout, LedgerEntry
from .serializers import (
    CreatePayoutSerializer,
    PayoutSerializer,
    MerchantSerializer,
    LedgerEntrySerializer,
)
from .services import create_payout, get_merchant_balance, InsufficientBalanceError
from .tasks import process_payout

logger = logging.getLogger(__name__)


class MerchantListView(APIView):
    def get(self, request):
        merchants = Merchant.objects.all().order_by('created_at')
        serializer = MerchantSerializer(merchants, many=True)
        return Response(serializer.data)


class MerchantDetailView(APIView):
    def get(self, request, merchant_id):
        merchant = get_object_or_404(Merchant, id=merchant_id)
        data = MerchantSerializer(merchant).data
        data['balance'] = get_merchant_balance(merchant)
        return Response(data)


class MerchantBalanceView(APIView):
    def get(self, request, merchant_id):
        merchant = get_object_or_404(Merchant, id=merchant_id)
        balance = get_merchant_balance(merchant)
        return Response(balance)


class MerchantLedgerView(APIView):
    def get(self, request, merchant_id):
        merchant = get_object_or_404(Merchant, id=merchant_id)
        entries = merchant.ledger_entries.all().order_by('-created_at')[:50]
        serializer = LedgerEntrySerializer(entries, many=True)
        return Response(serializer.data)


class PayoutListCreateView(APIView):
    def get(self, request, merchant_id):
        merchant = get_object_or_404(Merchant, id=merchant_id)
        payouts = merchant.payouts.all().order_by('-created_at')
        serializer = PayoutSerializer(payouts, many=True)
        return Response(serializer.data)

    def post(self, request, merchant_id):
        merchant = get_object_or_404(Merchant, id=merchant_id)

        idempotency_key = request.headers.get('Idempotency-Key', '').strip()
        if not idempotency_key:
            return Response(
                {'error': 'Idempotency-Key header is required.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        serializer = CreatePayoutSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        amount_paise = serializer.validated_data['amount_paise']
        bank_account_id = serializer.validated_data['bank_account_id']

        try:
            payout, created = create_payout(
                merchant=merchant,
                amount_paise=amount_paise,
                bank_account_id=bank_account_id,
                idempotency_key=idempotency_key,
            )
        except InsufficientBalanceError as e:
            return Response(
                {'error': str(e)},
                status=status.HTTP_422_UNPROCESSABLE_ENTITY
            )
        except Exception as e:
            logger.exception(f"[PayoutCreateView] Unexpected error: {e}")
            return Response(
                {'error': 'An unexpected error occurred.'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

        if created:
            try:
                process_payout.delay(str(payout.id))
            except Exception:
                pass

        response_status = status.HTTP_201_CREATED if created else status.HTTP_200_OK
        return Response(PayoutSerializer(payout).data, status=response_status)


class PayoutDetailView(APIView):
    def get(self, request, merchant_id, payout_id):
        merchant = get_object_or_404(Merchant, id=merchant_id)
        payout = get_object_or_404(Payout, id=payout_id, merchant=merchant)
        return Response(PayoutSerializer(payout).data)
class ProcessPayoutsView(APIView):
    """
    One-time endpoint to manually process pending payouts.
    Used for demo purposes on free tier without Celery.
    """
    def post(self, request):
        from django.db import transaction
        from django.utils import timezone

        pending = Payout.objects.filter(status=Payout.PENDING)
        count = pending.count()

        for payout in pending:
            with transaction.atomic():
                payout.status = Payout.COMPLETED
                payout.processed_at = timezone.now()
                payout.save()
                LedgerEntry.objects.create(
                    merchant=payout.merchant,
                    entry_type=LedgerEntry.DEBIT,
                    amount_paise=payout.amount_paise,
                    description=f"Payout to {payout.bank_account_id}",
                    reference_id=str(payout.id),
                )

        return Response({'processed': count})