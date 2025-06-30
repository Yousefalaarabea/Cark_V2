from django.urls import path
from . import views

app_name = 'wallets'

urlpatterns = [
    # User Wallet Endpoints
    path('balance/', views.WalletBalanceView.as_view(), name='wallet_balance'),
    path('transactions/', views.WalletTransactionHistoryView.as_view(), name='transaction_history'),
    path('transactions/summary/', views.WalletTransactionSummaryView.as_view(), name='transaction_summary'),
    path('recharge/', views.WalletRechargeView.as_view(), name='recharge_wallet'),
    path('withdraw/', views.WalletWithdrawalView.as_view(), name='withdraw_from_wallet'),
    path('withdraw/all/', views.WithdrawAllToMobileWalletView.as_view(), name='withdraw_all_to_mobile_wallet'),
    path('set-phone-wallet/', views.SetWalletPhoneNumberView.as_view(), name='set_wallet_phone_number'),
    path('transfer/', views.WalletTransferView.as_view(), name='transfer_between_wallets'),
    
    # Admin Endpoints
    path('admin/wallets/', views.AdminWalletListView.as_view(), name='admin_wallet_list'),
    path('admin/wallets/<int:pk>/', views.AdminWalletDetailView.as_view(), name='admin_wallet_detail'),
    path('admin/user/<int:user_id>/', views.AdminUserWalletDetailView.as_view(), name='admin_user_wallet_detail'),
    path('admin/withdrawals/', views.AdminWithdrawalListView.as_view(), name='admin_withdrawal_list'),
    path('admin/withdrawals/<int:withdrawal_id>/process/', views.AdminWithdrawalProcessView.as_view(), name='admin_process_withdrawal'),
    path('admin/withdrawals/<int:withdrawal_id>/cancel/', views.AdminWithdrawalCancelView.as_view(), name='admin_cancel_withdrawal'),
    
    # Webhook
    path('webhook/payment/', views.wallet_payment_webhook, name='wallet_payment_webhook'),
] 