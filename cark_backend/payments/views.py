from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, IsAdminUser
from rest_framework.decorators import api_view, authentication_classes, permission_classes
from django.views.decorators.csrf import csrf_exempt
from django.shortcuts import render, get_object_or_404
from django.contrib.auth import get_user_model
from django.db import IntegrityError
from django.conf import settings
from .services import paymob
import uuid
import hmac
import hashlib
import json
from .models import PaymentTransaction, SavedCard
from wallets.models import Wallet, WalletTransaction, TransactionType
from .serializers import (
    SavedCardSerializer, AddSavedCardSerializer, WalletSerializer,
    PaymentMethodSerializer, PaymentRequestSerializer, PaymentTransactionSerializer
)
from .services.payment_gateway import simulate_payment_gateway
from rentals.models import Rental, RentalPayment
from selfdrive_rentals.models import SelfDriveRental, SelfDrivePayment
from django.utils import timezone
from decimal import Decimal

User = get_user_model()


class StartPaymentView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        payment_method = request.data.get("payment_method")
        amount_cents = request.data.get("amount_cents")
        saved_card_token = request.data.get("saved_card_token")
        purpose = request.data.get("purpose")

        if not amount_cents:
            return Response({"error": "'amount_cents' is required."}, status=400)

        if not payment_method and not saved_card_token:
            return Response({"error": "Either 'payment_method' or 'saved_card_token' is required."}, status=400)

        try:
            amount_cents = int(amount_cents)
        except ValueError:
            return Response({"error": "Invalid 'amount_cents' value."}, status=400)

        reference = str(uuid.uuid4())
        user_id = str(request.user.id)
        if purpose == "wallet_recharge":
            merchant_order_id_with_user = f"wallet_recharge_{reference}_{user_id}"
        else:
            merchant_order_id_with_user = f"{reference}_{user_id}"

        try:
            auth_token = paymob.get_auth_token()
            order_id = paymob.create_order(auth_token, amount_cents, merchant_order_id_with_user)
        except Exception as e:
            return Response({"error": f"Paymob API error: {e}"}, status=500)

        try:
            transaction = PaymentTransaction.objects.create(
                user=request.user,
                merchant_order_id=merchant_order_id_with_user,
                paymob_order_id=order_id,
                amount_cents=amount_cents,
                currency="EGP",
                payment_method=payment_method if payment_method else "card",
                status="pending"
            )
        except IntegrityError:
            return Response({"error": "Duplicate transaction reference."}, status=409)

        if saved_card_token:
            integration_id = settings.PAYMOB_INTEGRATION_ID_MOTO
        elif payment_method == "wallet":
            integration_id = settings.PAYMOB_INTEGRATION_ID_WALLET
        else:
            integration_id = settings.PAYMOB_INTEGRATION_ID_CARD

        billing_data = {
            "apartment": "NA",
            "email": request.user.email or "user@example.com",
            "floor": "NA",
            "first_name": request.user.first_name or "Guest",
            "street": "NA",
            "building": "NA",
            "phone_number": getattr(request.user, 'phone_number', "01000000000"),
            "shipping_method": "NA",
            "postal_code": "NA",
            "city": "Cairo",
            "country": "EG",
            "last_name": request.user.last_name or "User",
            "state": "EG"
        }

        try:
            payment_token = paymob.get_payment_token(
                auth_token, order_id, amount_cents, billing_data, integration_id, saved_card_token
            )
        except Exception as e:
            transaction.status = "failed"
            transaction.message = f"Payment token error: {e}"
            transaction.save()
            return Response({"error": f"Payment token error: {e}"}, status=500)

        if saved_card_token:
            try:
                card = SavedCard.objects.filter(token=saved_card_token, user=request.user).first()
                if not card:
                    return Response({"error": "You do not own this card token."}, status=403)
                charge_response = paymob.charge_saved_card(saved_card_token, payment_token)
                print("PAYMOB CHARGE RESPONSE:", charge_response)
                success = charge_response.get("success", False)
                if isinstance(success, str):
                    success = success.lower() == "true"
                transaction.status = "completed" if success else "failed"
                transaction.success = success
                transaction.message = charge_response.get("message", "Charged saved card")
                transaction.save()
                return Response({
                    "success": success,
                    "order_id": order_id,
                    "merchant_order_id": merchant_order_id_with_user,
                    "charge_response": charge_response
                })
            except Exception as e:
                transaction.status = "failed"
                transaction.success = False
                transaction.message = f"Saved card charge failed: {e}"
                transaction.save()
                return Response({
                    "success": False,
                    "error": str(e),
                    "order_id": order_id,
                    "merchant_order_id": merchant_order_id_with_user
                }, status=500)

        iframe_url = f"https://accept.paymob.com/api/acceptance/iframes/{settings.PAYMOB_IFRAME_ID}?payment_token={payment_token}"
        return Response({
            "iframe_url": iframe_url,
            "order_id": order_id,
            "merchant_order_id": merchant_order_id_with_user
        })

User = get_user_model()

@csrf_exempt
@api_view(["POST"])
@authentication_classes([])  ## this point---------------------------------------------------
@permission_classes([])      ## this point---------------------------------------------------
def paymob_webhook(request):
    """
    This View receives the webhook from Paymob.
    It is used to verify the HMAC and update the transaction status in the database,
    and save the card token if a new card was paid with and requested to be saved.
    """
    try:
        raw_body = request.body.decode("utf-8")
        # print("🧾 Raw webhook body content:", raw_body) # Keep for full raw data
        if not raw_body.strip():
            print("Received empty body for webhook.")
            return Response({"error": "Empty body"}, status=400)
        data = json.loads(raw_body)
        print("Full decoded webhook data (JSON):", json.dumps(data, indent=4)) # For detailed debugging

    except json.JSONDecodeError as e:
        print(f"Failed to parse JSON body: {e}")
        return Response({"error": "Invalid JSON body"}, status=400)
    except Exception as e:
        print(f"An unexpected error occurred while parsing body: {e}")
        return Response({"error": "Failed to parse body"}, status=400)


    received_hmac = data.get("hmac") or request.query_params.get("hmac")
    if not received_hmac:
        print("❌ HMAC missing from webhook.")
        return Response({"error": "HMAC missing"}, status=400)

    webhook_type = data.get("type")

    # Initialize variables for safe access regardless of webhook type
    transaction_data = {}
    order_data = {}
    source_data = {}
    
    # Define a default response payload structure in case of non-transaction webhook
    response_payload = {
        "message": f"Acknowledged {webhook_type} webhook.",
        "status": "success" # Default success for acknowledged non-transaction webhooks
    }

    # --- NEW: Handle TOKEN webhook specifically for saving card ---
    if webhook_type == "TOKEN":
        print("Received TOKEN webhook. This usually means a token was created.")
        token_obj_data = data.get("obj", {})
        card_token = token_obj_data.get("token")
        card_brand = token_obj_data.get("card_subtype") # From your webhook log
        card_last_four_digits = token_obj_data.get("masked_pan", "").split('-')[-1] # Extract last 4 digits
        paymob_order_id = token_obj_data.get("order_id") # Order ID associated with the token

        if card_token and paymob_order_id:
            user_obj = None
            try:
                # Find the corresponding PaymentTransaction to get the user
                # We need to find the user based on the paymob_order_id
                transaction_in_db = PaymentTransaction.objects.filter(paymob_order_id=paymob_order_id).first()
                if transaction_in_db:
                    user_obj = transaction_in_db.user
                    print(f"Found user {user_obj.id} from existing transaction for Paymob order {paymob_order_id}.")
                else:
                    print(f"No existing transaction found for Paymob order {paymob_order_id} to link token to a user.")

            except Exception as e:
                print(f"❌ Error finding transaction for TOKEN webhook: {e}")

            if user_obj:
                try:
                    # ابحث عن كارت بنفس آخر 4 أرقام لهذا اليوزر فقط
                    existing_card = SavedCard.objects.filter(
                        user=user_obj,
                        card_last_four_digits=card_last_four_digits
                    ).first()
                    if existing_card:
                        # Update token and brand
                        existing_card.token = card_token
                        existing_card.card_brand = card_brand
                        existing_card.save()
                        print(f"🔄 Updated token for existing card (last 4: {card_last_four_digits}) for user {user_obj.id}.")
                        response_payload = {"message": "Card token updated for existing card.", "status": "success"}
                    else:
                        # أضف كارت جديد
                        SavedCard.objects.create(
                            user=user_obj,
                            token=card_token,
                            card_brand=card_brand,
                            card_last_four_digits=card_last_four_digits
                        )
                        print(f"💳 Saved new card (last 4: {card_last_four_digits}) for user {user_obj.id}.")
                        response_payload = {"message": "New card saved.", "status": "success"}
                except Exception as e:
                    print(f"❌ Error saving/updating card token for user {user_obj.id}: {e}")
                    response_payload = {"message": f"Error: {e}", "status": "fail"}
                    return Response(response_payload, status=500)
            else:
                print(f"⚠️ Could not save TOKEN webhook data: No user found for Paymob order ID {paymob_order_id}.")
                response_payload = {"message": "No user found for this card.", "status": "fail"}
                return Response(response_payload, status=400)
        else:
            print(f"⚠️ TOKEN webhook received but missing card_token or order_id: Token={card_token}, Order ID={paymob_order_id}.")

        response_payload = {"message": "Acknowledged TOKEN webhook and processed token save attempt.", "status": "success"}

    # --- Handle TRANSACTION webhook for payment status updates ---
    elif webhook_type == "TRANSACTION":
        transaction_data = data.get("obj", {})
        order_data = transaction_data.get("order", {})
        source_data = transaction_data.get("source_data", {})

        # List of fields required by Paymob for HMAC (alphabetically sorted)
        required_fields = [
            "amount_cents", "created_at", "currency", "error_occured",
            "has_parent_transaction", "id", "integration_id", "is_3d_secure",
            "is_auth", "is_capture", "is_refunded", "is_standalone_payment",
            "is_voided", "order", "owner", "pending",
            "source_data_pan", "source_data_sub_type", "source_data_type", "success"
        ]

        # Build a flat dictionary from the received data to create the string for HMAC
        flat_data = {
            "amount_cents": str(transaction_data.get("amount_cents", "")),
            "created_at": str(transaction_data.get("created_at", "")),
            "currency": str(transaction_data.get("currency", "")),
            "error_occured": str(transaction_data.get("error_occured", False)).lower(),
            "has_parent_transaction": str(transaction_data.get("has_parent_transaction", False)).lower(),
            "id": str(transaction_data.get("id", "")),
            "integration_id": str(transaction_data.get("integration_id", "")),
            "is_3d_secure": str(transaction_data.get("is_3d_secure", False)).lower(),
            "is_auth": str(transaction_data.get("is_auth", False)).lower(),
            "is_capture": str(transaction_data.get("is_capture", False)).lower(),
            "is_refunded": str(transaction_data.get("is_refunded", False)).lower(),
            "is_standalone_payment": str(transaction_data.get("is_standalone_payment", False)).lower(),
            "is_voided": str(transaction_data.get("is_voided", False)).lower(),
            "order": str(order_data.get("id", "")),
            "owner": str(transaction_data.get("owner", "")),
            "pending": str(transaction_data.get("pending", False)).lower(),
            "source_data_pan": str(source_data.get("pan", "")),
            "source_data_sub_type": str(source_data.get("sub_type", "")),
            "source_data_type": str(source_data.get("type", "")),
            "success": str(transaction_data.get("success", False)).lower()
        }

        # Build the string from required fields in alphabetical order
        concat_str = ""
        for key in required_fields:
            value = flat_data.get(key, "")
            concat_str += value

        generated_hmac = hmac.new(
            settings.PAYMOB_HMAC_SECRET.encode(),
            concat_str.encode(),
            hashlib.sha512
        ).hexdigest()

        if received_hmac != generated_hmac:
            print("❌ Invalid HMAC – Rejected!")
            return Response({"error": "Invalid HMAC"}, status=401)

        print("✅ Webhook HMAC verified successfully for TRANSACTION type.")

        # Extract merchant_order_id and user ID from it
        merchant_order_id = order_data.get("merchant_order_id", "")
        parts = merchant_order_id.split('_')
        user_uuid = parts[-1] if len(parts) > 1 else None

        user_obj = None
        if user_uuid:
            try:
                user_obj = User.objects.get(id=user_uuid)
            except User.DoesNotExist:
                print(f"User with ID {user_uuid} not found for transaction {merchant_order_id}. Cannot link transaction to user.")

        # Save/update the transaction in the database
        try:
            transaction_obj, created = PaymentTransaction.objects.update_or_create(
                merchant_order_id=merchant_order_id,
                defaults={
                    'user': user_obj,
                    'paymob_transaction_id': transaction_data.get("id"),
                    'paymob_order_id': order_data.get("id"),
                    'amount_cents': transaction_data.get("amount_cents"),
                    'currency': transaction_data.get("currency"),
                    'success': transaction_data.get("success", False),
                    'message': transaction_data.get("data.message", "No specific message"),
                    'status': "completed" if transaction_data.get("success", False) else "failed",
                    'card_type': source_data.get("type"),
                    'card_pan': source_data.get("pan"),
                    'payment_method': 'card' if source_data.get("type") else 'wallet',
                }
            )
            if created:
                print(f"➕ Created new transaction entry for {merchant_order_id}.")
            else:
                print(f"🔄 Updated existing transaction entry for {merchant_order_id}.")

        except Exception as e:
            print(f"❌ Error saving/updating transaction in DB from webhook: {e}")
            return Response({"error": "Internal server error during transaction update."}, status=500)
        
        # NOTE: Token saving logic is now primarily in the 'TOKEN' webhook handler.
        # The 'is_tokenized' field in TRANSACTION webhooks isn't consistently present for your setup.
        # So we remove the token saving logic here to avoid redundancy/confusion.

        # Update the response payload for TRANSACTION type webhook
        response_payload = {
            "message": "✅ Webhook processed successfully",
            "transaction_id": transaction_data.get("id"),
            "amount_cents": transaction_data.get("amount_cents"),
            "currency": transaction_data.get("currency"),
            "created_at": transaction_data.get("created_at"),
            "success": transaction_data.get("success"),
            "merchant_order_id": order_data.get("merchant_order_id"),
            "paymob_order_id": order_data.get("id"),
            "card_type": source_data.get("type"),
            "card_pan": source_data.get("pan"),
        }

        # لو الغرض شحن المحفظة وتم الدفع بنجاح، زود الرصيد
        if merchant_order_id.startswith("wallet_recharge") and transaction_data.get("success", False):
            wallet = Wallet.objects.get(user=user_obj)
            amount_egp = Decimal(str(transaction_data.get("amount_cents", 0))) / Decimal('100')
            balance_before = wallet.balance
            wallet.balance += amount_egp
            wallet.save()
            print(f"✅ Wallet recharged for user {user_obj.id} by {amount_egp} EGP.")
            # إضافة سجل في WalletTransaction
            transaction_type, _ = TransactionType.objects.get_or_create(name='شحن محفظة عبر فيزا')
            WalletTransaction.objects.create(
                wallet=wallet,
                transaction_type=transaction_type,
                amount=amount_egp,
                balance_before=balance_before,
                balance_after=wallet.balance,
                status='completed',
                description='شحن المحفظة عن طريق Paymob',
                reference_id=transaction_obj.id,
                reference_type='payment'
            )

    else:
        print(f"Ignored webhook type: {webhook_type}.")
        response_payload = {"message": f"Ignored non-transaction or token webhook type: {webhook_type}.", "status": "success"}

    # Return the appropriate response payload
    return Response(response_payload, status=200)


class SavedCardsView(APIView):
    """
    API to display saved cards for the current user.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        saved_cards = SavedCard.objects.filter(user=request.user)
        serializer_data = []
        for card in saved_cards:
            serializer_data.append({
                "token": card.token,
                "card_brand": card.card_brand,
                "card_last_four_digits": card.card_last_four_digits,
                "id": card.id # Add ID for easier selection from frontend
            })
        return Response(serializer_data, status=200)

class AddSavedCardView(APIView):
    permission_classes = [IsAuthenticated]
    def post(self, request):
        serializer = AddSavedCardSerializer(data=request.data)
        if serializer.is_valid():
            card = serializer.save(user=request.user)
            return Response(SavedCardSerializer(card).data, status=201)
        return Response(serializer.errors, status=400)

class ListPaymentMethodsView(APIView):
    permission_classes = [IsAuthenticated]
    def get(self, request):
        cards = SavedCard.objects.filter(user=request.user)
        wallet = Wallet.objects.get(user=request.user)
        methods = []
        for card in cards:
            methods.append({
                'type': 'card',
                'id': card.id,
                'card_brand': card.card_brand,
                'card_last_four_digits': card.card_last_four_digits
            })
        if wallet.phone_wallet_number:  # فقط لو فيه رقم محفظة
            methods.append({
                'type': 'wallet',
                'id': wallet.id,
                'balance': wallet.balance,
                'phone_wallet_number': wallet.phone_wallet_number
            })
        return Response(methods)

class PayView(APIView):
    permission_classes = [IsAuthenticated]
    def post(self, request):
        serializer = PaymentRequestSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=400)
        data = serializer.validated_data
        amount = data['amount']
        method_type = data['payment_method_type']
        method_id = data['payment_method_id']
        payment_for = data['payment_for']
        rental_type = data['rental_type']
        rental_id = data['rental_id']
        user = request.user
        # تحقق من وسيلة الدفع
        if method_type == 'wallet':
            wallet = get_object_or_404(Wallet, id=method_id, user=user)
            if wallet.balance < amount:
                return Response({'detail': 'Insufficient wallet balance', 'status': 'fail404'}, status=400)
        elif method_type == 'card':
            card = get_object_or_404(SavedCard, id=method_id, user=user)
        else:
            return Response({'detail': 'Invalid payment method', 'status': 'fail404'}, status=400)
        # محاكاة الدفع
        try:
            if method_type == 'wallet':
                wallet.balance -= amount
                wallet.save()
                payment_response = simulate_payment_gateway(amount, 'wallet', user)
            else:
                payment_response = simulate_payment_gateway(amount, 'card', user, card_token=card.token)
        except Exception as e:
            return Response({'detail': str(e), 'status': 'fail404'}, status=500)
        # حفظ PaymentTransaction
        transaction = PaymentTransaction.objects.create(
            user=user,
            merchant_order_id=f"{rental_type}_{rental_id}_{timezone.now().timestamp()}",
            amount_cents=int(amount * 100),
            currency='EGP',
            success=payment_response.success,
            message=payment_response.message,
            payment_method=method_type,
            status=payment_response.status,
            card_type=getattr(card, 'card_brand', None) if method_type == 'card' else None,
            card_pan=getattr(card, 'card_last_four_digits', None) if method_type == 'card' else None,
            paymob_transaction_id=payment_response.transaction_id,
            paymob_order_id=None
        )
        # ربط الدفع بالـ Rental أو SelfDriveRental
        if rental_type == 'rental':
            rental = get_object_or_404(Rental, id=rental_id)
            RentalPayment.objects.create(
                rental=rental,
                user=user,
                amount=amount,
                status=payment_response.status,
                paid_at=payment_response.paid_at,
                transaction=transaction
            )
        elif rental_type == 'selfdrive':
            rental = get_object_or_404(SelfDriveRental, id=rental_id)
            SelfDrivePayment.objects.create(
                rental=rental,
                user=user,
                amount=amount,
                status=payment_response.status,
                paid_at=payment_response.paid_at,
                transaction=transaction
            )
        return Response({
            'status': payment_response.status,
            'transaction_id': payment_response.transaction_id,
            'paid_at': payment_response.paid_at,
            'success': payment_response.success,
            'message': payment_response.message
        })

class AdminPaymentTransactionsView(APIView):
    permission_classes = [IsAdminUser]
    def get(self, request):
        transactions = PaymentTransaction.objects.all().order_by('-created_at')
        serializer = PaymentTransactionSerializer(transactions, many=True)
        return Response(serializer.data)

class ChargeSavedCardView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        saved_card_token = request.data.get("saved_card_token")
        amount_cents = request.data.get("amount_cents")
        if not saved_card_token or not amount_cents:
            return Response({"error": "saved_card_token and amount_cents are required."}, status=400)
        # تحقق من ملكية التوكن قبل أي بروسيس
        card = SavedCard.objects.filter(token=saved_card_token, user=request.user).first()
        if not card:
            return Response({"error": "You do not own this card token."}, status=403)
        try:
            amount_cents = int(amount_cents)
        except ValueError:
            return Response({"error": "Invalid amount_cents value."}, status=400)

        reference = str(uuid.uuid4())
        user_id = str(request.user.id)
        merchant_order_id_with_user = f"{reference}_{user_id}"

        try:
            auth_token = paymob.get_auth_token()
            order_id = paymob.create_order(auth_token, amount_cents, merchant_order_id_with_user)
            integration_id = settings.PAYMOB_INTEGRATION_ID_MOTO
            billing_data = {
                "apartment": "NA",
                "email": request.user.email or "user@example.com",
                "floor": "NA",
                "first_name": request.user.first_name or "Guest",
                "street": "NA",
                "building": "NA",
                "phone_number": getattr(request.user, 'phone_number', "01000000000"),
                "shipping_method": "NA",
                "postal_code": "NA",
                "city": "Cairo",
                "country": "EG",
                "last_name": request.user.last_name or "User",
                "state": "EG"
            }
            payment_token = paymob.get_payment_token(
                auth_token, order_id, amount_cents, billing_data, integration_id, saved_card_token
            )
            charge_response = paymob.charge_saved_card(saved_card_token, payment_token)
            print("PAYMOB CHARGE RESPONSE:", charge_response)
            success = charge_response.get("success", False)
            if isinstance(success, str):
                success = success.lower() == "true"

            # جلب بيانات الكارت من response لو متاحة
            card_type = charge_response.get("source_data.sub_type") or getattr(card, 'card_brand', None)
            card_pan = charge_response.get("source_data.pan") or getattr(card, 'card_last_four_digits', None)

            PaymentTransaction.objects.create(
                user=request.user,
                merchant_order_id=merchant_order_id_with_user,
                paymob_order_id=order_id,
                amount_cents=amount_cents,
                currency="EGP",
                payment_method="card",
                status="completed" if success else "failed",
                success=success,
                message=charge_response.get("message", "Charged saved card"),
                card_type=card_type,
                card_pan=card_pan,
                paymob_transaction_id=charge_response.get("id")
            )

            return Response({
                "success": success,
                "order_id": order_id,
                "merchant_order_id": merchant_order_id_with_user,
                "charge_response": charge_response
            })
        except Exception as e:
            return Response({"success": False, "error": str(e)}, status=500)

class WalletRechargeView(StartPaymentView):
    """
    API لشحن المحفظة باستخدام نفس منطق StartPaymentView مع إضافة منطق شحن المحفظة بعد نجاح الدفع.
    """
    def post(self, request, *args, **kwargs):
        response = super().post(request, *args, **kwargs)
        # لو الدفع نجح (success=True) وresponse فيه order_id وamount_cents
        # تم تعليق منطق شحن المحفظة هنا لتفادي تكرار الشحن، حيث يتم الشحن فعليًا في الـ webhook فقط
        # if response.status_code == 200 and response.data.get("success"):
        #     amount_cents = int(request.data.get("amount_cents"))
        #     amount_egp = Decimal(str(amount_cents)) / Decimal('100')
        #     wallet = Wallet.objects.get(user=request.user)
        #     balance_before = wallet.balance
        #     wallet.balance += amount_egp
        #     wallet.save()
        #     transaction_type, _ = TransactionType.objects.get_or_create(name='شحن محفظة عبر فيزا')
        #     WalletTransaction.objects.create(
        #         wallet=wallet,
        #         transaction_type=transaction_type,
        #         amount=amount_egp,
        #         balance_before=balance_before,
        #         balance_after=wallet.balance,
        #         status='completed',
        #         description='شحن المحفظة عن طريق Paymob (مباشر)',
        #         reference_type='payment'
        #     )
        return response


