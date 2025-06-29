from decimal import Decimal
from django.db import transaction
from django.contrib.auth import get_user_model
from .models import Wallet, WalletTransaction, WalletRecharge, WalletWithdrawal, TransactionType
from .serializers import WalletTransferSerializer

User = get_user_model()

class WalletService:
    """خدمة إدارة المحفظة"""
    
    @staticmethod
    def get_or_create_wallet(user):
        """الحصول على محفظة المستخدم أو إنشاء واحدة جديدة"""
        wallet, created = Wallet.objects.get_or_create(user=user)
        return wallet
    
    @staticmethod
    def get_wallet_balance(user):
        """الحصول على رصيد محفظة المستخدم"""
        wallet = WalletService.get_or_create_wallet(user)
        return wallet.balance
    
    @staticmethod
    @transaction.atomic
    def add_funds_to_wallet(user, amount, transaction_type_name, description="", reference_id="", reference_type=""):
        """إضافة أموال للمحفظة"""
        wallet = WalletService.get_or_create_wallet(user)
        
        # الحصول على نوع المعاملة أو إنشاؤه
        transaction_type, created = TransactionType.objects.get_or_create(
            name=transaction_type_name,
            defaults={'is_credit': True, 'description': description}
        )
        
        # حساب الأرصيد
        balance_before = Decimal(str(wallet.balance))
        balance_after = balance_before + Decimal(str(amount))
        
        # إنشاء المعاملة مع الأرصيد المحسوبة مسبقاً
        wallet_transaction = WalletTransaction.objects.create(
            wallet=wallet,
            transaction_type=transaction_type,
            amount=amount,
            balance_before=balance_before,
            balance_after=balance_after,
            status='completed',
            description=description,
            reference_id=reference_id,
            reference_type=reference_type
        )
        
        # تحديث رصيد المحفظة
        wallet.balance = balance_after
        wallet.save()
        
        return wallet_transaction
    
    @staticmethod
    @transaction.atomic
    def deduct_funds_from_wallet(user, amount, transaction_type_name, description="", reference_id="", reference_type=""):
        """خصم أموال من المحفظة"""
        wallet = WalletService.get_or_create_wallet(user)
        
        # التحقق من كفاية الرصيد
        if wallet.balance < amount:
            raise ValueError("الرصيد غير كافي")
        
        # الحصول على نوع المعاملة أو إنشاؤه
        transaction_type, created = TransactionType.objects.get_or_create(
            name=transaction_type_name,
            defaults={'is_credit': False, 'description': description}
        )
        
        # حساب الأرصيد
        balance_before = Decimal(str(wallet.balance))
        balance_after = balance_before - Decimal(str(amount))
        
        # إنشاء المعاملة مع الأرصيد المحسوبة مسبقاً
        wallet_transaction = WalletTransaction.objects.create(
            wallet=wallet,
            transaction_type=transaction_type,
            amount=amount,
            balance_before=balance_before,
            balance_after=balance_after,
            status='completed',
            description=description,
            reference_id=reference_id,
            reference_type=reference_type
        )
        
        # تحديث رصيد المحفظة
        wallet.balance = balance_after
        wallet.save()
        
        return wallet_transaction
    
    @staticmethod
    @transaction.atomic
    def transfer_between_wallets(sender, recipient_email, amount, description=""):
        """تحويل بين المحافظ"""
        # التحقق من صحة البيانات
        try:
            recipient = User.objects.get(email=recipient_email)
        except User.DoesNotExist:
            raise ValueError("المستخدم المستلم غير موجود")
        
        if sender == recipient:
            raise ValueError("لا يمكن التحويل لنفس المستخدم")
        
        # خصم من محفظة المرسل
        debit_transaction = WalletService.deduct_funds_from_wallet(
            sender, 
            amount, 
            "تحويل لمستخدم آخر",
            f"تحويل لـ {recipient.email} - {description}"
        )
        
        # إضافة لمحفظة المستلم
        credit_transaction = WalletService.add_funds_to_wallet(
            recipient, 
            amount, 
            "تحويل من مستخدم آخر",
            f"تحويل من {sender.email} - {description}"
        )
        
        return {
            'debit_transaction': debit_transaction,
            'credit_transaction': credit_transaction
        }

class WalletRechargeService:
    """خدمة شحن المحفظة"""
    
    @staticmethod
    def create_recharge_request(user, amount, method, description=""):
        """إنشاء طلب شحن"""
        wallet = WalletService.get_or_create_wallet(user)
        
        recharge = WalletRecharge.objects.create(
            wallet=wallet,
            amount=amount,
            method=method,
            description=description
        )
        
        return recharge
    
    @staticmethod
    @transaction.atomic
    def process_recharge_payment(recharge_id, payment_transaction):
        """معالجة دفع الشحن"""
        try:
            recharge = WalletRecharge.objects.get(id=recharge_id)
            
            if recharge.status != 'pending':
                raise ValueError("طلب الشحن غير صالح للمعالجة")
            
            # تحديث حالة الشحن
            recharge.status = 'processing'
            recharge.payment_transaction = payment_transaction
            recharge.save()
            
            # إذا كان الدفع ناجح، أضف الأموال للمحفظة
            if payment_transaction.success:
                wallet_transaction = WalletService.add_funds_to_wallet(
                    recharge.wallet.user,
                    recharge.amount,
                    f"شحن محفظة - {recharge.get_method_display()}",
                    recharge.description,
                    str(payment_transaction.id),
                    "payment"
                )
                
                recharge.status = 'completed'
                recharge.save()
                
                return {
                    'recharge': recharge,
                    'wallet_transaction': wallet_transaction
                }
            else:
                recharge.status = 'failed'
                recharge.save()
                return {'recharge': recharge}
                
        except WalletRecharge.DoesNotExist:
            raise ValueError("طلب الشحن غير موجود")

class WalletWithdrawalService:
    """خدمة سحب من المحفظة"""
    
    @staticmethod
    def create_withdrawal_request(user, amount, method, bank_account="", bank_name="", description=""):
        """إنشاء طلب سحب"""
        wallet = WalletService.get_or_create_wallet(user)
        
        # التحقق من كفاية الرصيد
        if wallet.balance < amount:
            raise ValueError("الرصيد غير كافي")
        
        withdrawal = WalletWithdrawal.objects.create(
            wallet=wallet,
            amount=amount,
            method=method,
            bank_account=bank_account,
            bank_name=bank_name,
            description=description
        )
        
        return withdrawal
    
    @staticmethod
    @transaction.atomic
    def process_withdrawal(withdrawal_id, admin_user=None):
        """معالجة طلب السحب (بواسطة الإدارة)"""
        try:
            withdrawal = WalletWithdrawal.objects.get(id=withdrawal_id)
            
            if withdrawal.status != 'pending':
                raise ValueError("طلب السحب غير صالح للمعالجة")
            
            # خصم الأموال من المحفظة
            wallet_transaction = WalletService.deduct_funds_from_wallet(
                withdrawal.wallet.user,
                withdrawal.amount,
                f"سحب من محفظة - {withdrawal.get_method_display()}",
                withdrawal.description,
                str(withdrawal.id),
                "withdrawal"
            )
            
            # تحديث حالة السحب
            withdrawal.status = 'completed'
            withdrawal.save()
            
            return {
                'withdrawal': withdrawal,
                'wallet_transaction': wallet_transaction
            }
            
        except WalletWithdrawal.DoesNotExist:
            raise ValueError("طلب السحب غير موجود")
    
    @staticmethod
    def cancel_withdrawal(withdrawal_id, admin_user=None):
        """إلغاء طلب السحب"""
        try:
            withdrawal = WalletWithdrawal.objects.get(id=withdrawal_id)
            
            if withdrawal.status != 'pending':
                raise ValueError("لا يمكن إلغاء طلب السحب")
            
            withdrawal.status = 'cancelled'
            withdrawal.save()
            
            return withdrawal
            
        except WalletWithdrawal.DoesNotExist:
            raise ValueError("طلب السحب غير موجود")

class WalletTransactionService:
    """خدمة معاملات المحفظة"""
    
    @staticmethod
    def get_user_transactions(user, limit=50, offset=0):
        """الحصول على معاملات المستخدم"""
        wallet = WalletService.get_or_create_wallet(user)
        
        transactions = WalletTransaction.objects.filter(
            wallet=wallet
        ).order_by('-created_at')[offset:offset+limit]
        
        return transactions
    
    @staticmethod
    def get_transaction_summary(user, days=30):
        """الحصول على ملخص المعاملات"""
        from django.utils import timezone
        from datetime import timedelta
        
        wallet = WalletService.get_or_create_wallet(user)
        end_date = timezone.now()
        start_date = end_date - timedelta(days=days)
        
        transactions = WalletTransaction.objects.filter(
            wallet=wallet,
            created_at__range=[start_date, end_date],
            status='completed'
        )
        
        total_credit = sum(t.amount for t in transactions if t.transaction_type.is_credit)
        total_debit = sum(t.amount for t in transactions if not t.transaction_type.is_credit)
        
        return {
            'total_credit': total_credit,
            'total_debit': total_debit,
            'net_amount': total_credit - total_debit,
            'transaction_count': transactions.count(),
            'period_days': days
        } 