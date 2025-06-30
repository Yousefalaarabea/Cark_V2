import requests
from django.conf import settings
import json

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
