from rest_framework import serializers
from .models import SavedCard, PaymentTransaction
from wallets.models import Wallet

class SavedCardSerializer(serializers.ModelSerializer):
    class Meta:
        model = SavedCard
        fields = ['id', 'card_brand', 'card_last_four_digits', 'created_at']

class AddSavedCardSerializer(serializers.ModelSerializer):
    class Meta:
        model = SavedCard
        fields = ['token', 'card_brand', 'card_last_four_digits']

class WalletSerializer(serializers.ModelSerializer):
    class Meta:
        model = Wallet
        fields = ['id', 'balance', 'phone_wallet_number']

class PaymentMethodSerializer(serializers.Serializer):
    type = serializers.ChoiceField(choices=['wallet', 'card'])
    id = serializers.CharField()
    card_brand = serializers.CharField(required=False)
    card_last_four_digits = serializers.CharField(required=False)
    balance = serializers.DecimalField(max_digits=10, decimal_places=2, required=False)
    phone_wallet_number = serializers.CharField(required=False)

class PaymentRequestSerializer(serializers.Serializer):
    amount = serializers.DecimalField(max_digits=10, decimal_places=2)
    payment_method_type = serializers.ChoiceField(choices=['wallet', 'card'])
    payment_method_id = serializers.CharField()  # wallet id or card id
    payment_for = serializers.ChoiceField(choices=['deposit', 'remaining', 'excess'])
    rental_type = serializers.ChoiceField(choices=['rental', 'selfdrive'])
    rental_id = serializers.CharField()

class PaymentTransactionSerializer(serializers.ModelSerializer):
    class Meta:
        model = PaymentTransaction
        fields = ['id', 'amount_cents', 'currency', 'success', 'message', 'created_at', 'payment_method', 'status', 'card_type', 'card_pan']
