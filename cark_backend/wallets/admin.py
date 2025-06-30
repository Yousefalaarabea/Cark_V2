from django.contrib import admin
from .models import Wallet, WalletTransaction, WalletRecharge, WalletWithdrawal, TransactionType

@admin.register(TransactionType)
class TransactionTypeAdmin(admin.ModelAdmin):
    list_display = ['name', 'is_credit', 'description']
    list_filter = ['is_credit']
    search_fields = ['name', 'description']
    ordering = ['name']

@admin.register(Wallet)
class WalletAdmin(admin.ModelAdmin):
    list_display = ['user', 'balance', 'is_active', 'created_at']
    list_filter = ['is_active', 'created_at']
    search_fields = ['user__email', 'user__first_name', 'user__last_name']
    readonly_fields = ['created_at', 'updated_at']
    ordering = ['-created_at']
    
    def get_queryset(self, request):
        return super().get_queryset(request).select_related('user')

@admin.register(WalletTransaction)
class WalletTransactionAdmin(admin.ModelAdmin):
    list_display = ['id', 'wallet', 'transaction_type', 'amount', 'status', 'created_at']
    list_filter = ['status', 'transaction_type__is_credit', 'created_at']
    search_fields = ['wallet__user__email', 'description', 'reference_id']
    readonly_fields = ['id', 'balance_before', 'balance_after', 'created_at', 'updated_at']
    ordering = ['-created_at']
    
    def get_queryset(self, request):
        return super().get_queryset(request).select_related('wallet__user', 'transaction_type')

@admin.register(WalletRecharge)
class WalletRechargeAdmin(admin.ModelAdmin):
    list_display = ['id', 'wallet', 'amount', 'method', 'status', 'created_at']
    list_filter = ['status', 'method', 'created_at']
    search_fields = ['wallet__user__email', 'description']
    readonly_fields = ['created_at', 'updated_at']
    ordering = ['-created_at']
    
    def get_queryset(self, request):
        return super().get_queryset(request).select_related('wallet__user', 'payment_transaction')
    
    actions = ['approve_recharge', 'reject_recharge']
    
    def approve_recharge(self, request, queryset):
        """موافقة على طلبات الشحن"""
        for recharge in queryset.filter(status='pending'):
            try:
                from .services import WalletRechargeService
                if recharge.payment_transaction and recharge.payment_transaction.success:
                    WalletRechargeService.process_recharge_payment(recharge.id, recharge.payment_transaction)
                    self.message_user(request, f"تمت الموافقة على شحن المحفظة {recharge.id}")
                else:
                    self.message_user(request, f"لا يمكن الموافقة على شحن المحفظة {recharge.id} - الدفع غير ناجح", level='ERROR')
            except Exception as e:
                self.message_user(request, f"خطأ في معالجة شحن المحفظة {recharge.id}: {str(e)}", level='ERROR')
    
    approve_recharge.short_description = "موافقة على طلبات الشحن المحددة"
    
    def reject_recharge(self, request, queryset):
        """رفض طلبات الشحن"""
        updated = queryset.filter(status='pending').update(status='cancelled')
        self.message_user(request, f"تم رفض {updated} طلب شحن")

@admin.register(WalletWithdrawal)
class WalletWithdrawalAdmin(admin.ModelAdmin):
    list_display = ['id', 'wallet', 'amount', 'method', 'status', 'created_at']
    list_filter = ['status', 'method', 'created_at']
    search_fields = ['wallet__user__email', 'bank_account', 'bank_name', 'description']
    readonly_fields = ['created_at', 'updated_at']
    ordering = ['-created_at']
    
    def get_queryset(self, request):
        return super().get_queryset(request).select_related('wallet__user')
    
    actions = ['process_withdrawal', 'cancel_withdrawal']
    
    def process_withdrawal(self, request, queryset):
        """معالجة طلبات السحب"""
        for withdrawal in queryset.filter(status='pending'):
            try:
                from .services import WalletWithdrawalService
                WalletWithdrawalService.process_withdrawal(withdrawal.id, request.user)
                self.message_user(request, f"تمت معالجة طلب السحب {withdrawal.id}")
            except Exception as e:
                self.message_user(request, f"خطأ في معالجة طلب السحب {withdrawal.id}: {str(e)}", level='ERROR')
    
    process_withdrawal.short_description = "معالجة طلبات السحب المحددة"
    
    def cancel_withdrawal(self, request, queryset):
        """إلغاء طلبات السحب"""
        for withdrawal in queryset.filter(status='pending'):
            try:
                from .services import WalletWithdrawalService
                WalletWithdrawalService.cancel_withdrawal(withdrawal.id, request.user)
                self.message_user(request, f"تم إلغاء طلب السحب {withdrawal.id}")
            except Exception as e:
                self.message_user(request, f"خطأ في إلغاء طلب السحب {withdrawal.id}: {str(e)}", level='ERROR')
    
    cancel_withdrawal.short_description = "إلغاء طلبات السحب المحددة"
