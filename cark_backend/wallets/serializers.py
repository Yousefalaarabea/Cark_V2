from rest_framework import serializers
from .models import Wallet, WalletTransaction, WalletRecharge, WalletWithdrawal, TransactionType
from django.contrib.auth import get_user_model

User = get_user_model()

class UserSerializer(serializers.ModelSerializer):
    """Serializer للمستخدم"""
    class Meta:
        model = User
        fields = ['id', 'email', 'first_name', 'last_name', 'phone_number']

class TransactionTypeSerializer(serializers.ModelSerializer):
    """Serializer لأنواع المعاملات"""
    class Meta:
        model = TransactionType
        fields = '__all__'

class WalletSerializer(serializers.ModelSerializer):
    """Serializer للمحفظة"""
    user = UserSerializer(read_only=True)
    balance = serializers.DecimalField(max_digits=10, decimal_places=2, read_only=True)
    
    class Meta:
        model = Wallet
        fields = ['id', 'user', 'balance', 'is_active', 'created_at', 'updated_at']
        read_only_fields = ['id', 'created_at', 'updated_at']

class WalletTransactionSerializer(serializers.ModelSerializer):
    """Serializer لمعاملات المحفظة"""
    wallet = WalletSerializer(read_only=True)
    transaction_type = TransactionTypeSerializer(read_only=True)
    transaction_type_id = serializers.PrimaryKeyRelatedField(
        queryset=TransactionType.objects.all(),
        source='transaction_type',
        write_only=True
    )
    
    class Meta:
        model = WalletTransaction
        fields = [
            'id', 'wallet', 'transaction_type', 'transaction_type_id',
            'amount', 'balance_before', 'balance_after', 'status',
            'description', 'reference_id', 'reference_type', 'created_at'
        ]
        read_only_fields = ['id', 'wallet', 'balance_before', 'balance_after', 'created_at']

class WalletRechargeSerializer(serializers.ModelSerializer):
    """Serializer لشحن المحفظة"""
    wallet = WalletSerializer(read_only=True)
    
    class Meta:
        model = WalletRecharge
        fields = [
            'id', 'wallet', 'amount', 'method', 'status',
            'payment_transaction', 'description', 'created_at'
        ]
        read_only_fields = ['id', 'wallet', 'status', 'created_at']

    def validate_amount(self, value):
        """التحقق من صحة المبلغ"""
        if value <= 0:
            raise serializers.ValidationError("المبلغ يجب أن يكون أكبر من صفر")
        return value

class WalletWithdrawalSerializer(serializers.ModelSerializer):
    """Serializer لسحب من المحفظة"""
    wallet = WalletSerializer(read_only=True)
    
    class Meta:
        model = WalletWithdrawal
        fields = [
            'id', 'wallet', 'amount', 'method', 'status',
            'bank_account', 'bank_name', 'description', 'created_at'
        ]
        read_only_fields = ['id', 'wallet', 'status', 'created_at']

    def validate_amount(self, value):
        """التحقق من صحة المبلغ"""
        if value <= 0:
            raise serializers.ValidationError("المبلغ يجب أن يكون أكبر من صفر")
        return value

    def validate(self, data):
        """التحقق من صحة البيانات"""
        wallet = self.context.get('wallet')
        if wallet and data.get('amount', 0) > wallet.balance:
            raise serializers.ValidationError("الرصيد غير كافي للسحب")
        return data

class WalletBalanceSerializer(serializers.ModelSerializer):
    """Serializer لعرض رصيد المحفظة فقط"""
    user = UserSerializer(read_only=True)
    
    class Meta:
        model = Wallet
        fields = ['id', 'user', 'balance', 'is_active']

class WalletTransactionHistorySerializer(serializers.ModelSerializer):
    """Serializer لتاريخ معاملات المحفظة"""
    transaction_type = TransactionTypeSerializer(read_only=True)
    
    class Meta:
        model = WalletTransaction
        fields = [
            'id', 'transaction_type', 'amount', 'balance_before', 
            'balance_after', 'status', 'description', 'reference_id', 
            'reference_type', 'created_at'
        ]

class WalletRechargeRequestSerializer(serializers.Serializer):
    """Serializer لطلب شحن المحفظة"""
    amount = serializers.DecimalField(max_digits=10, decimal_places=2)
    method = serializers.ChoiceField(choices=WalletRecharge.RECHARGE_METHOD)
    description = serializers.CharField(max_length=500, required=False, allow_blank=True)

    def validate_amount(self, value):
        if value <= 0:
            raise serializers.ValidationError("المبلغ يجب أن يكون أكبر من صفر")
        return value

class WalletWithdrawalRequestSerializer(serializers.Serializer):
    """Serializer لطلب سحب من المحفظة"""
    amount = serializers.DecimalField(max_digits=10, decimal_places=2)
    method = serializers.ChoiceField(choices=WalletWithdrawal.WITHDRAWAL_METHOD)
    bank_account = serializers.CharField(max_length=255, required=False, allow_blank=True)
    bank_name = serializers.CharField(max_length=100, required=False, allow_blank=True)
    description = serializers.CharField(max_length=500, required=False, allow_blank=True)
    phone_number = serializers.CharField(max_length=20, required=False, allow_blank=True)

    def validate_amount(self, value):
        if value <= 0:
            raise serializers.ValidationError("المبلغ يجب أن يكون أكبر من صفر")
        return value

    def validate(self, data):
        if data.get('method') == 'bank_transfer':
            if not data.get('bank_account') or not data.get('bank_name'):
                raise serializers.ValidationError("معلومات الحساب البنكي مطلوبة للتحويل البنكي")
        return data

class WalletTransferSerializer(serializers.Serializer):
    """Serializer لتحويل بين المحافظ"""
    recipient_email = serializers.EmailField()
    amount = serializers.DecimalField(max_digits=10, decimal_places=2)
    description = serializers.CharField(max_length=500, required=False, allow_blank=True)

    def validate_amount(self, value):
        if value <= 0:
            raise serializers.ValidationError("المبلغ يجب أن يكون أكبر من صفر")
        return value

    def validate_recipient_email(self, value):
        try:
            User.objects.get(email=value)
        except User.DoesNotExist:
            raise serializers.ValidationError("المستخدم غير موجود")
        return value

class WithdrawAllToMobileWalletSerializer(serializers.Serializer):
    phone_number = serializers.CharField(max_length=20, required=False, allow_blank=True)
    description = serializers.CharField(max_length=255, required=False, allow_blank=True)

    def validate(self, data):
        # Reject any extra fields
        allowed = {'phone_number', 'description'}
        extra = set(self.initial_data.keys()) - allowed
        if extra:
            raise serializers.ValidationError(f"حقول غير مسموح بها: {', '.join(extra)}")
        return data

class WalletPhoneNumberSerializer(serializers.Serializer):
    phone_wallet_number = serializers.CharField(max_length=20) 