import requests
from django.conf import settings
import json
import uuid

def get_auth_token():
    try:
        response = requests.post(f"{settings.PAYMOB_BASE_URL}/auth/tokens", json={
            "api_key": settings.PAYMOB_API_KEY
        })
        response.raise_for_status()
        return response.json()["token"]
    except requests.exceptions.RequestException as e:
        print(f"Error getting Paymob auth token: {e}")
        raise 

def create_order(auth_token, amount_cents, reference):
    try:
        response = requests.post(f"{settings.PAYMOB_BASE_URL}/ecommerce/orders", json={
            "auth_token": auth_token,
            "delivery_needed": False, 
            "amount_cents": amount_cents,
            "currency": "EGP",
            "items": [], 
            "merchant_order_id": f"{reference}" 
        })
        response.raise_for_status()
        return response.json()["id"]
    except requests.exceptions.RequestException as e:
        print(f"Error creating Paymob order: {e}")
        raise

def get_payment_token(auth_token, order_id, amount_cents, billing_data, integration_id, saved_card_token=None):
    payload = {
        "auth_token": auth_token,
        "amount_cents": amount_cents,
        "expiration": 3600,
        "order_id": order_id,
        "currency": "EGP",
        "integration_id": integration_id,
        "lock_order_when_paid": True,
        "tokenization_enabled": True,
        "billing_data": billing_data
    }


    print(f"DEBUG: Full payload to payment_keys: {json.dumps(payload, indent=4)}")

    try:
        response = requests.post(f"{settings.PAYMOB_BASE_URL}/acceptance/payment_keys", json=payload)
        response.raise_for_status()
        return response.json()["token"]
    except requests.exceptions.RequestException as e:
        print(f"Error getting Paymob payment token: {e}")
        if hasattr(e, 'response') and e.response is not None:
            print(f"Paymob error response: {e.response.text}")
        raise

def charge_saved_card(saved_card_token,payment_token):
    url = f"https://accept.paymob.com/api/acceptance/payments/pay"
    payload = {
        "source": {"identifier": saved_card_token, "subtype": "TOKEN"},
        "payment_token": payment_token
    }
    try:
        response = requests.post(url, json=payload)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        print(f"Error charging saved card: {e}")
        if hasattr(e, 'response') and e.response is not None:
            print(f"Post pay error: {e.response.text}")
        raise

def create_payment_intent_for_deposit(amount_cents, user, rental_id):
    """
    Creates a payment intent for deposit payment with new card (returns iframe URL)
    Similar to self-drive rental implementation
    """
    try:
        # 1. Get Paymob auth token
        auth_token = get_auth_token()
        
        # 2. Create unique reference and order
        reference = str(uuid.uuid4())
        user_id = str(user.id)
        merchant_order_id_with_user = f"rental_deposit_{rental_id}_{reference}_{user_id}"
        order_id = create_order(auth_token, amount_cents, merchant_order_id_with_user)
        
        # 3. Integration ID for new card payments
        integration_id = settings.PAYMOB_INTEGRATION_ID_CARD
        
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
        payment_token = get_payment_token(
            auth_token, order_id, amount_cents, billing_data, integration_id
        )
        
        # 6. Create iframe URL
        iframe_url = f"https://accept.paymob.com/api/acceptance/iframes/{settings.PAYMOB_IFRAME_ID}?payment_token={payment_token}"
        
        return {
            'success': True,
            'iframe_url': iframe_url,
            'order_id': order_id,
            'payment_token': payment_token,
            'merchant_order_id': merchant_order_id_with_user
        }
        
    except Exception as e:
        return {
            'success': False,
            'message': f'Failed to create payment intent: {str(e)}'
        }
