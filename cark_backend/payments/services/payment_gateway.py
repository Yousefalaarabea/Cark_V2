import time
import uuid
from datetime import datetime
from django.conf import settings
from . import paymob

class PaymentGatewayResponse:
    def __init__(self, success, transaction_id, message, paid_at, status):
        self.success = success
        self.transaction_id = transaction_id
        self.message = message
        self.paid_at = paid_at
        self.status = status

    def to_dict(self):
        return {
            'success': self.success,
            'transaction_id': self.transaction_id,
            'message': self.message,
            'paid_at': self.paid_at,
            'status': self.status,
        }

def simulate_payment_gateway(amount, payment_method, user, card_token=None):
    """
    Simulate a payment request to an external gateway (e.g., Paymob).
    Always returns success for now, but structure allows for future failure simulation.
    """
    time.sleep(1)  # Simulate network delay
    transaction_id = str(uuid.uuid4())
    paid_at = datetime.now()
    status = 'completed'
    message = f"Payment of {amount} EGP via {payment_method} successful."
    return PaymentGatewayResponse(
        success=True,
        transaction_id=transaction_id,
        message=message,
        paid_at=paid_at,
        status=status
    )

def pay_with_saved_card_gateway(amount_cents, user, saved_card_token):
    """
    Execute a real payment using Paymob with a saved card token.
    Returns a dict with all payment details (success, transaction_id, message, paid_at, status, charge_response, etc).
    """
    try:
        # 1. Get Paymob auth token
        auth_token = paymob.get_auth_token()
        # 2. Create Paymob order
        reference = str(uuid.uuid4())
        user_id = str(user.id)
        merchant_order_id_with_user = f"{reference}_{user_id}"
        order_id = paymob.create_order(auth_token, amount_cents, merchant_order_id_with_user)
        # 3. Integration ID for saved card (usually MOTO)
        integration_id = settings.PAYMOB_INTEGRATION_ID_MOTO
        # 4. Billing data from user
        billing_data = {
            "apartment": "NA",
            "email": getattr(user, 'email', None) or "user@example.com",
            "floor": "NA",
            "first_name": getattr(user, 'first_name', None) or "Guest",
            "street": "NA",
            "building": "NA",
            "phone_number": getattr(user, 'phone_number', "01000000000"),
            "shipping_method": "NA",
            "postal_code": "NA",
            "city": "Cairo",
            "country": "EG",
            "last_name": getattr(user, 'last_name', None) or "User",
            "state": "EG"
        }
        # 5. Get payment token
        payment_token = paymob.get_payment_token(
            auth_token, order_id, amount_cents, billing_data, integration_id, saved_card_token
        )
        # 6. Charge saved card
        charge_response = paymob.charge_saved_card(saved_card_token, payment_token)
        # 7. Parse response
        success = charge_response.get("success", False)
        if isinstance(success, str):
            success = success.lower() == "true"
        status = charge_response.get("pending", False)
        if success:
            status = "completed"
        elif charge_response.get("pending", False):
            status = "pending"
        else:
            status = "failed"
        paid_at = datetime.now() if success else None
        message = charge_response.get("message") or charge_response.get("data", {}).get("message") or str(charge_response)
        transaction_id = charge_response.get("id") or charge_response.get("txn_response_code")
        # Return all details
        return {
            "success": success,
            "transaction_id": transaction_id,
            "message": message,
            "paid_at": paid_at,
            "status": status,
            "charge_response": charge_response,
            "order_id": order_id,
            "merchant_order_id": merchant_order_id_with_user
        }
    except Exception as e:
        return {
            "success": False,
            "transaction_id": None,
            "message": f"Payment failed: {e}",
            "paid_at": None,
            "status": "failed",
            "charge_response": None
        } 