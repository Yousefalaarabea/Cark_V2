from django.db import models
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from decimal import Decimal
import uuid

User = get_user_model()

class Wallet(models.Model):
    """
    نموذج المحفظة الداخلية للمستخدم
    """
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='wallet')
    balance = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'))
    is_active = models.BooleanField(default=True)
    phone_wallet_number = models.CharField(max_length=20, blank=True, null=True)  # رقم محفظة الهاتف
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "محفظة"
        verbose_name_plural = "محافظ"

    def __str__(self):
        return f"محفظة {self.user.email} - الرصيد: {self.balance}"

    def add_funds(self, amount):
        """إضافة أموال للمحفظة"""
        if amount <= 0:
            raise ValidationError("المبلغ يجب أن يكون أكبر من صفر")
        # Ensure both values are Decimal
        current_balance = Decimal(str(self.balance))
        amount_decimal = Decimal(str(amount))
        self.balance = current_balance + amount_decimal
        self.save()

    def deduct_funds(self, amount):
        """خصم أموال من المحفظة"""
        if amount <= 0:
            raise ValidationError("المبلغ يجب أن يكون أكبر من صفر")
        # Ensure both values are Decimal
        current_balance = Decimal(str(self.balance))
        amount_decimal = Decimal(str(amount))
        if current_balance < amount_decimal:
            raise ValidationError("الرصيد غير كافي")
        self.balance = current_balance - amount_decimal
        self.save()

    def get_balance(self):
        """الحصول على الرصيد الحالي"""
        return self.balance

class TransactionType(models.Model):
    """
    أنواع المعاملات المالية
    """
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    is_credit = models.BooleanField(default=True)  # True for credit, False for debit
    
    class Meta:
        verbose_name = "نوع المعاملة"
        verbose_name_plural = "أنواع المعاملات"

    def __str__(self):
        return self.name

class WalletTransaction(models.Model):
    """
    نموذج معاملات المحفظة
    """
    TRANSACTION_STATUS = [
        ('pending', 'قيد الانتظار'),
        ('completed', 'مكتمل'),
        ('failed', 'فشل'),
        ('cancelled', 'ملغي'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    wallet = models.ForeignKey(Wallet, on_delete=models.CASCADE, related_name='transactions')
    transaction_type = models.ForeignKey(TransactionType, on_delete=models.CASCADE)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    balance_before = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'))
    balance_after = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'))
    status = models.CharField(max_length=20, choices=TRANSACTION_STATUS, default='pending')
    description = models.TextField(blank=True)
    reference_id = models.CharField(max_length=255, blank=True, help_text="معرف مرجعي للمعاملة الخارجية")
    reference_type = models.CharField(max_length=50, blank=True, help_text="نوع المرجع (مثل: rental, payment, etc.)")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "معاملة محفظة"
        verbose_name_plural = "معاملات المحفظة"
        ordering = ['-created_at']

    def __str__(self):
        return f"معاملة {self.id} - {self.amount} - {self.status}"

    def save(self, *args, **kwargs):
        if not self.pk:  # New transaction
            # Only calculate balance fields if they're not already set
            if self.balance_before == Decimal('0.00'):
                self.balance_before = Decimal(str(self.wallet.balance))
            if self.balance_after == Decimal('0.00'):
                amount_decimal = Decimal(str(self.amount))
                if self.transaction_type.is_credit:
                    self.balance_after = self.balance_before + amount_decimal
                else:
                    self.balance_after = self.balance_before - amount_decimal
        super().save(*args, **kwargs)

class WalletRecharge(models.Model):
    """
    نموذج شحن المحفظة
    """
    RECHARGE_STATUS = [
        ('pending', 'قيد الانتظار'),
        ('processing', 'قيد المعالجة'),
        ('completed', 'مكتمل'),
        ('failed', 'فشل'),
        ('cancelled', 'ملغي'),
    ]

    RECHARGE_METHOD = [
        ('card', 'بطاقة ائتمان'),
        ('bank_transfer', 'تحويل بنكي'),
        ('cash', 'نقدي'),
        ('wallet_transfer', 'تحويل من محفظة أخرى'),
    ]

    wallet = models.ForeignKey(Wallet, on_delete=models.CASCADE, related_name='recharges')
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    method = models.CharField(max_length=20, choices=RECHARGE_METHOD)
    status = models.CharField(max_length=20, choices=RECHARGE_STATUS, default='pending')
    payment_transaction = models.ForeignKey('payments.PaymentTransaction', on_delete=models.SET_NULL, null=True, blank=True)
    description = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "شحن محفظة"
        verbose_name_plural = "شحنات المحفظة"
        ordering = ['-created_at']

    def __str__(self):
        return f"شحن {self.amount} - {self.status}"

class WalletWithdrawal(models.Model):
    """
    نموذج سحب من المحفظة
    """
    WITHDRAWAL_STATUS = [
        ('pending', 'قيد الانتظار'),
        ('processing', 'قيد المعالجة'),
        ('completed', 'مكتمل'),
        ('failed', 'فشل'),
        ('cancelled', 'ملغي'),
    ]

    WITHDRAWAL_METHOD = [
        ('bank_transfer', 'تحويل بنكي'),
        ('cash', 'نقدي'),
        ('wallet_transfer', 'تحويل لمحفظة أخرى'),
    ]

    wallet = models.ForeignKey(Wallet, on_delete=models.CASCADE, related_name='withdrawals')
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    method = models.CharField(max_length=20, choices=WITHDRAWAL_METHOD)
    status = models.CharField(max_length=20, choices=WITHDRAWAL_STATUS, default='pending')
    bank_account = models.CharField(max_length=255, blank=True, help_text="رقم الحساب البنكي")
    bank_name = models.CharField(max_length=100, blank=True, help_text="اسم البنك")
    description = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "سحب من محفظة"
        verbose_name_plural = "سحوبات المحفظة"
        ordering = ['-created_at']

    def __str__(self):
        return f"سحب {self.amount} - {self.status}"
