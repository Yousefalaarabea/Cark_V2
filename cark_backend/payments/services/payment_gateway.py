import time
import uuid
from datetime import datetime

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