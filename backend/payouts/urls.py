from django.urls import path
from . import views

urlpatterns = [
    # Merchants
    path('merchants/', views.MerchantListView.as_view()),
    path('merchants/<uuid:merchant_id>/', views.MerchantDetailView.as_view()),
    path('merchants/<uuid:merchant_id>/balance/', views.MerchantBalanceView.as_view()),
    path('merchants/<uuid:merchant_id>/ledger/', views.MerchantLedgerView.as_view()),

    # Payouts
    path('merchants/<uuid:merchant_id>/payouts/', views.PayoutListCreateView.as_view()),
    path('merchants/<uuid:merchant_id>/payouts/<uuid:payout_id>/', views.PayoutDetailView.as_view()),
    path('process-payouts/', views.ProcessPayoutsView.as_view()),
]