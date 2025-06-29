from django.db import models
from django.contrib.auth import get_user_model

User = get_user_model()

class PaymentTransaction(models.Model):
    """
    Model to store details of each payment transaction.
    Used to track payment status, amount, and card information (if it's a card).
    """
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='transactions', help_text="The user who performed the transaction.")
    merchant_order_id = models.CharField(max_length=255, unique=True, help_text="Your internal store order ID.")
    paymob_transaction_id = models.CharField(max_length=255, unique=True, null=True, blank=True, help_text="Transaction ID from Paymob.")
    paymob_order_id = models.CharField(max_length=255, null=True, blank=True, help_text="Order ID from Paymob.")
    amount_cents = models.IntegerField(help_text="Amount in cents (e.g., 7000 for 70 EGP).")
    currency = models.CharField(max_length=10, default="EGP", help_text="Currency, defaults to EGP.")
    success = models.BooleanField(default=False, help_text="Was the transaction successful?")
    message = models.TextField(null=True, blank=True, help_text="Error or success message from Paymob.")
    created_at = models.DateTimeField(auto_now_add=True, help_text="Timestamp of when the transaction record was created.")
    updated_at = models.DateTimeField(auto_now=True, help_text="Timestamp of the last update to the transaction record.")
    payment_method = models.CharField(max_length=50, null=True, blank=True, help_text="Payment method (e.g., 'card' or 'wallet').")
    status = models.CharField(max_length=50, default="pending", help_text="Transaction status (e.g., 'pending', 'completed', 'failed').")
    card_type = models.CharField(max_length=50, null=True, blank=True, help_text="Type of card (e.g., 'Visa', 'MasterCard').")
    card_pan = models.CharField(max_length=50, null=True, blank=True, help_text="Last 4 digits of the card number.")

    class Meta:
        verbose_name = "Payment Transaction"
        verbose_name_plural = "Payment Transactions"
        unique_together = ('user', 'merchant_order_id') # Ensure no duplicate transactions for the same user with the same merchant order ID

    def __str__(self):
        return f"Transaction {self.merchant_order_id} - {self.status} for {self.user.username}"

class SavedCard(models.Model):
    """
    Model to store saved card tokens for each user.
    Allows users to pay later without re-entering card details.
    """
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='saved_cards', help_text="The user to whom the saved card belongs.")
    token = models.CharField(max_length=255, unique=True, help_text="The card token provided by Paymob.")
    card_brand = models.CharField(max_length=50, null=True, blank=True, help_text="Brand of the card (e.g., 'Visa', 'MasterCard').")
    card_last_four_digits = models.CharField(max_length=4, null=True, blank=True, help_text="Last four digits of the card.")
    created_at = models.DateTimeField(auto_now_add=True, help_text="Timestamp of when the card was saved.")

    class Meta:
        verbose_name = "Saved Card"
        verbose_name_plural = "Saved Cards"
        unique_together = ('user', 'token') # Ensure the same card token isn't saved multiple times for the same user

    def __str__(self):
        return f"{self.card_brand} ending in {self.card_last_four_digits} for {self.user.username}"

