from django.http import HttpResponse
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from .models import Rental, RentalPayment, PlannedTrip, PlannedTripStop, RentalBreakdown, RentalLog
from .serializers import RentalSerializer, RentalCreateUpdateSerializer, PlannedTripStopSerializer, RentalBreakdownSerializer
from .services import calculate_rental_financials, dummy_charge_visa, dummy_charge_visa_or_wallet
from cars.models import Car
from django.shortcuts import get_object_or_404
from django.db import transaction
from django.utils import timezone
from datetime import timedelta
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated

def home(request):
    return HttpResponse("Welcome to Rentals Home!")  # type: ignore

class RentalViewSet(viewsets.ModelViewSet):
    """
    ViewSet رئيسي لإدارة جميع خطوات فلو الإيجار مع السائق:
    - إنشاء الحجز
    - حساب التكاليف
    - تأكيد الحجز
    - بدء الرحلة
    - تأكيد الوصول للمحطات
    - إنهاء الانتظار
    - إنهاء الرحلة
    - توزيع الأرباح
    """
    permission_classes = [IsAuthenticated]
    queryset = Rental.objects.all()  # type: ignore
    serializer_class = RentalSerializer

    def get_serializer_class(self):
        if self.action in ['create', 'update', 'partial_update']:
            return RentalCreateUpdateSerializer
        return RentalSerializer

    def create(self, request, *args, **kwargs):
        """
        إنشاء حجز جديد مع محطات الرحلة.
        """
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        with transaction.atomic():
            rental = serializer.save(renter=request.user)
            planned_km = float(request.data.get('planned_km', 0))
            total_waiting_minutes = int(request.data.get('total_waiting_minutes', 0))
            self.create_rental_breakdown(rental, planned_km, total_waiting_minutes)
            
            deposit_amount = 0
            remaining_amount = 0
            if hasattr(rental, 'breakdown'):
                deposit_amount = rental.breakdown.deposit
                # المبلغ المتبقي = الفاينل كوست - الديبوزيت
                remaining_amount = rental.breakdown.final_cost - deposit_amount
                
            payment, _ = RentalPayment.objects.get_or_create(
                rental=rental,
                defaults={
                    'deposit_amount': deposit_amount,
                    'deposit_paid_status': 'Pending',
                    'rental_paid_status': 'Pending',
                    'payment_method': rental.payment_method,
                    'remaining_amount': remaining_amount,
                }
            )
            payment.remaining_amount = remaining_amount
            payment.save()
            
            # Log the rental creation
            RentalLog.objects.create(
                rental=rental,
                event='Rental created',
                performed_by_type='Renter',
                performed_by=request.user
            )
            
            # Send notification to car owner
            from notifications.models import Notification
            Notification.objects.create(
                receiver=rental.car.owner,
                title="طلب حجز جديد",
                message=f"طلب حجز جديد لسيارتك {rental.car.brand} {rental.car.model} من {rental.pickup_address}",
                notification_type="RENTAL",
                data={
                    'rental_id': rental.id,
                    'pickup_address': rental.pickup_address,
                    'event': 'rental_created'
                }
            )
        
        # ===== RESPONSE =====
        
        return Response({
            'status': 'success',
            'message': 'تم إنشاء الحجز بنجاح.',
            'details': {
                'rental_id': rental.id,
                'rental_status': rental.status,
                'car_details': {
                    'brand': rental.car.brand,
                    'model': rental.car.model,
                    'year': rental.car.year,
                    'owner_name': rental.car.owner.get_full_name() or rental.car.owner.username
                },
                'trip_details': {
                    'pickup_address': rental.pickup_address,
                    'dropoff_address': rental.dropoff_address,
                    'start_date': rental.start_date,
                    'end_date': rental.end_date,
                    'planned_km': planned_km,
                    'total_waiting_minutes': total_waiting_minutes
                },
                'payment_info': {
                    'deposit_amount': float(deposit_amount),
                    'remaining_amount': float(remaining_amount),
                    'payment_method': rental.payment_method
                }
            },
            'next_actions': [
                'Owner must confirm booking',
                'After confirmation, renter must pay deposit'
            ],
            'trip_progress': {
                'current_step': 'Rental Created',
                'completed_steps': [
                    'Rental Created'
                ],
                'remaining_steps': [
                    'Owner Confirmation',
                    'Deposit Payment',
                    'Owner Arrival Confirmation',
                    'Renter On Way',
                    'Start Trip',
                    'Trip Stops',
                    'End Trip'
                ]
            },
            'rental_data': RentalSerializer(rental).data
        }, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['post'])
    def calculate_costs(self, request, pk=None):
        """
        حساب التكاليف التفصيلية للرحلة (أجرة، كيلومترات إضافية، انتظار، بوفر، عربون...)
        """
        rental = self.get_object()
        planned_km = float(request.data.get('planned_km', 0))
        total_waiting_minutes = int(request.data.get('total_waiting_minutes', 0))
        create_rental_breakdown(rental, planned_km, total_waiting_minutes)
        from .models import RentalPayment
        payment, _ = RentalPayment.objects.get_or_create(rental=rental)
        payment.deposit_amount = rental.breakdown.deposit
        payment.payment_method = rental.payment_method
        # المبلغ المتبقي = الفاينل كوست - الديبوزيت
        payment.remaining_amount = rental.breakdown.final_cost - rental.breakdown.deposit
        payment.save()
        breakdown = rental.breakdown
        return Response(RentalBreakdownSerializer(breakdown).data)

    @action(detail=True, methods=['post'])
    def confirm_booking(self, request, pk=None):
        """
        تأكيد الحجز من المالك فقط (بدون دفع)
        الخطوات التالية: المالك → تأكيد → المستأجر يدفع العربون
        """
        rental = self.get_object()
        
        # ===== VALIDATIONS =====
        
        # 1. Check rental status
        if rental.status != 'PendingOwnerConfirmation':
            return Response({
                'error_code': 'INVALID_STATUS', 
                'error_message': 'لا يمكن تأكيد الحجز إلا عندما تكون الحالة في انتظار تأكيد المالك.',
                'details': {
                    'rental_id': rental.id,
                    'current_status': rental.status,
                    'required_status': 'PendingOwnerConfirmation'
                }
            }, status=400)
        
        # 2. Check owner permission
        if rental.car.owner != request.user:
            return Response({
                'error_code': 'NOT_OWNER', 
                'error_message': 'فقط مالك السيارة يمكنه تأكيد الحجز.',
                'details': {
                    'rental_id': rental.id,
                    'car_owner': rental.car.owner.id,
                    'current_user': request.user.id
                }
            }, status=403)
        
        # ===== PROCESSING =====
        
        # Change status to require deposit payment
        old_status = rental.status
        rental.status = 'DepositRequired'
        rental.save()
        
        # Set deposit due date (24 hours)
        from .models import RentalPayment
        payment, _ = RentalPayment.objects.get_or_create(rental=rental)
        payment.deposit_due_at = timezone.now() + timedelta(days=1)
        payment.save()
        
        # Log the confirmation
        RentalLog.objects.create(
            rental=rental, 
            event='Booking confirmed by owner', 
            performed_by_type='Owner', 
            performed_by=request.user
        )
        
        # Send notification to renter
        from notifications.models import Notification
        Notification.objects.create(
            receiver=rental.renter,
            title="تم تأكيد الحجز",
            message=f"تم تأكيد حجزك لسيارة {rental.car.brand} {rental.car.model}. يرجى دفع العربون خلال 24 ساعة.",
            notification_type="RENTAL",
            data={
                'rental_id': rental.id,
                'deposit_amount': float(payment.deposit_amount or 0),
                'event': 'booking_confirmed'
            }
        )
        
        # ===== RESPONSE =====
        
        return Response({
            'status': 'success',
            'message': 'تم تأكيد الحجز بنجاح.',
            'details': {
                'rental_id': rental.id,
                'old_status': old_status,
                'new_status': rental.status,
                'deposit_due_at': payment.deposit_due_at,
                'car_details': {
                    'brand': rental.car.brand,
                    'model': rental.car.model,
                    'year': rental.car.year
                },
                'renter_info': {
                    'name': rental.renter.get_full_name() or rental.renter.email,
                    'phone': rental.renter.phone_number
                },
                'deposit_info': {
                    'amount': float(payment.deposit_amount or 0),
                    'due_at': payment.deposit_due_at
                }
            },
            'next_actions': [
                'Renter must pay deposit within 24 hours',
                'After deposit payment, owner can confirm arrival'
            ],
            'trip_progress': {
                'current_step': 'Booking Confirmed',
                'completed_steps': [
                    'Rental Created',
                    'Owner Confirmed Booking'
                ],
                'remaining_steps': [
                    'Deposit Payment',
                    'Owner Arrival Confirmation',
                    'Renter On Way',
                    'Start Trip',
                    'Trip Stops',
                    'End Trip'
                ]
            }
        })

    @action(detail=True, methods=['post'])
    def owner_confirm_arrival(self, request, pk=None):
        """
        تأكيد وصول المالك لموقع الاستلام (pickup location)
        """
        rental = self.get_object()
        
        # ===== VALIDATIONS =====
        
        # 1. Check if user is the car owner
        if rental.car.owner != request.user:
            return Response({
                'error_code': 'NOT_OWNER',
                'error_message': 'فقط مالك السيارة يمكنه تأكيد الوصول.',
                'details': {
                    'rental_id': rental.id,
                    'car_owner': rental.car.owner.id,
                    'current_user': request.user.id
                }
            }, status=403)
        
        # 2. Check rental status
        if rental.status != 'Confirmed':
            return Response({
                'error_code': 'INVALID_STATUS',
                'error_message': 'Trip can only be started after deposit is paid and booking is confirmed.',
                'current_status': rental.status,
                'required_status': 'Confirmed',
                'next_actions': {
                    'PendingOwnerConfirmation': 'Wait for owner to confirm booking',
                    'DepositRequired': 'Renter must pay deposit first'
                }
            }, status=400)
        
        # 3. Check if already confirmed
        if rental.owner_arrival_confirmed:
            return Response({
                'error_code': 'ALREADY_CONFIRMED',
                'error_message': 'تم تأكيد الوصول بالفعل.',
                'details': {
                    'rental_id': rental.id,
                    'confirmed_at': rental.owner_arrived_at_pickup,
                    'pickup_address': rental.pickup_address
                }
            }, status=400)
        
        # ===== PROCESSING =====
        
        # Update rental with arrival confirmation
        rental.owner_arrival_confirmed = True
        rental.owner_arrived_at_pickup = timezone.now()
        rental.save()
        
        # Log the event
        RentalLog.objects.create(
            rental=rental,
            event='Owner confirmed arrival at pickup location',
            performed_by_type='Owner',
            performed_by=request.user
        )
        
        # Send notification to renter
        from notifications.models import Notification
        Notification.objects.create(
            receiver=rental.renter,
            title="السائق وصل",
            message=f"السائق وصل إلى {rental.pickup_address}. يمكن بدء الرحلة الآن.",
            notification_type="RENTAL",
            data={
                'rental_id': rental.id,
                'pickup_address': rental.pickup_address,
                'event': 'owner_arrival_confirmed'
            }
        )
        
        # ===== RESPONSE =====
        
        return Response({
            'status': 'success',
            'message': 'تم تأكيد وصول السائق بنجاح.',
            'details': {
                'rental_id': rental.id,
                'confirmed_at': rental.owner_arrived_at_pickup,
                'pickup_address': rental.pickup_address,
                'car_details': {
                    'brand': rental.car.brand,
                    'model': rental.car.model,
                    'year': rental.car.year
                },
                'renter_info': {
                    'name': rental.renter.get_full_name() or rental.renter.email,
                    'phone': rental.renter.phone_number
                }
            },
            'next_actions': [
                'Renter can now announce "I am on my way"',
                'Trip can be started when renter arrives'
            ],
            'trip_progress': {
                'current_step': 'Owner Arrival Confirmed',
                'completed_steps': [
                    'Rental Created',
                    'Owner Confirmed Booking',
                    'Deposit Paid',
                    'Owner Arrival Confirmed'
                ],
                'remaining_steps': [
                    'Renter On Way',
                    'Start Trip',
                    'Trip Stops',
                    'End Trip'
                ]
            }
        })

    @action(detail=True, methods=['post'])
    def deposit_payment(self, request, pk=None):
        """
        دفع العربون بكارت محفوظ (نفس نظام self-drive)
        صفحة منفصلة بطرق دفع منفصلة
        """
        rental = self.get_object()
        
        # ===== BASIC VALIDATIONS (same as self-drive) =====
        
        # 1. Check if owner confirmed first and deposit is still required
        if rental.status == 'PendingOwnerConfirmation':
            return Response({
                'error_code': 'OWNER_CONFIRMATION_REQUIRED',
                'error_message': f'يجب أن يؤكد مالك السيارة الحجز أولاً قبل دفع العربون. الحالة الحالية: {rental.status}'
            }, status=400)
        
        if rental.status == 'Confirmed':
            return Response({
                'error_code': 'DEPOSIT_ALREADY_PAID',
                'error_message': f'تم دفع العربون بالفعل. الحالة الحالية: {rental.status}'
            }, status=400)
        
        if rental.status not in ['DepositRequired']:
            return Response({
                'error_code': 'INVALID_STATUS',
                'error_message': f'لا يمكن دفع العربون في هذه الحالة. الحالة الحالية: {rental.status}'
            }, status=400)
        
        # 2. Check user is renter
        if rental.renter != request.user:
            return Response({
                'error_code': 'NOT_RENTER',
                'error_message': 'يجب أن تكون المستأجر في هذا الحجز.'
            }, status=403)
        
        # 3. Check if already paid - get payment record
        from .models import RentalPayment
        try:
            payment = RentalPayment.objects.get(rental=rental)
            if payment.deposit_paid_status == 'Paid':
                return Response({
                    'error_code': 'ALREADY_PAID',
                    'error_message': 'تم دفع العربون بالفعل ولا يمكن دفعه مرة أخرى.',
                    'transaction_id': payment.deposit_transaction_id,
                    'paid_at': payment.deposit_paid_at
                }, status=400)
        except RentalPayment.DoesNotExist:
            payment = RentalPayment.objects.create(rental=rental)
        
        # 4. Check breakdown exists and deposit amount
        if not hasattr(rental, 'breakdown'):
            return Response({
                'error_code': 'PAYMENT_NOT_FOUND',
                'error_message': 'لا يوجد بيانات دفع مرتبطة بهذا الحجز.'
            }, status=400)
        
        deposit_amount = rental.breakdown.deposit
        
        # ===== REQUEST VALIDATION (same as self-drive) =====
        
        # Get and validate payment details
        payment_method = request.data.get('payment_method')
        saved_card_id = request.data.get('saved_card_id')
        amount_cents = request.data.get('amount_cents')
        payment_type = request.data.get('type', 'deposit')  # deposit/remaining/excess
        
        # Only handle saved_card deposit payments (same as self-drive)
        if payment_method == 'saved_card' and saved_card_id and amount_cents and payment_type == 'deposit':
            try:
                # --- VALIDATION (same as self-drive) ---
                from payments.models import SavedCard
                from payments.services.payment_gateway import pay_with_saved_card_gateway
                
                # 1. Check card exists and belongs to user
                try:
                    card = SavedCard.objects.get(id=saved_card_id, user=request.user)
                except SavedCard.DoesNotExist:
                    return Response({
                        'error_code': 'CARD_NOT_FOUND',
                        'error_message': 'الكارت غير موجود أو لا يخصك.'
                    }, status=404)
                
                # 2. Check deposit amount matches required amount
                if not hasattr(payment, 'deposit_amount') or not payment.deposit_amount:
                    payment.deposit_amount = deposit_amount
                    payment.save()
                
                required_cents = int(round(float(payment.deposit_amount) * 100))
                if int(amount_cents) != required_cents:
                    return Response({
                        'error_code': 'INVALID_AMOUNT',
                        'error_message': f'المبلغ المطلوب للعربون هو {required_cents} قرش.'
                    }, status=400)
                
                # --- PAYMENT PROCESSING (same as self-drive) ---
                result = pay_with_saved_card_gateway(int(amount_cents), request.user, card.token)
                if not result['success']:
                    return Response({
                        'error_code': 'PAYMENT_FAILED',
                        'error_message': result['message'],
                        'details': result.get('charge_response')
                    }, status=400)
                
                # Update payment status
                payment.deposit_paid_status = 'Paid'
                payment.deposit_paid_at = timezone.now()
                payment.deposit_transaction_id = result['transaction_id']
                payment.payment_method = 'visa'  # Same as self-drive
                payment.save()
                
                # Change rental status from DepositRequired to Confirmed
                old_status = rental.status
                rental.status = 'Confirmed'
                rental.save()
                
                # Log the status change
                from .models import RentalLog
                RentalLog.objects.create(
                    rental=rental,
                    event='Deposit payment completed',
                    performed_by_type='Renter',
                    performed_by=request.user
                )
                
                # Send notification to owner
                from notifications.models import Notification
                Notification.objects.create(
                    receiver=rental.car.owner,
                    title="Deposit Paid",
                    message=f"Deposit paid for rental of {rental.car.brand} {rental.car.model}. Ready for pickup confirmation.",
                    notification_type="PAYMENT",
                    data={'rental_id': rental.id, 'pickup_address': rental.pickup_address}
                )
                
                # Return success response (same format as self-drive)
                from .serializers import RentalPaymentSerializer
                return Response({
                    'status': 'deposit payment processed successfully.',
                    'transaction_id': result['transaction_id'],
                    'payment': RentalPaymentSerializer(payment).data,
                    'paymob_details': result,
                    'old_status': old_status,
                    'new_status': rental.status
                })
                
            except Exception as e:
                return Response({
                    'error_code': 'PAYMENT_ERROR',
                    'error_message': str(e)
                }, status=500)

        # Default response for invalid payment method (same as self-drive)
        return Response({
            'error_code': 'INVALID_PAYMENT_METHOD', 
            'error_message': 'طريقة الدفع غير صحيحة أو بيانات مفقودة. يجب استخدام saved_card مع saved_card_id و amount_cents.',
            'required_parameters': {
                'payment_method': 'saved_card',
                'saved_card_id': 'integer',
                'amount_cents': 'integer',
                'type': 'deposit'
            }
        }, status=400)

    @action(detail=True, methods=['post'])
    def new_card_deposit_payment(self, request, pk=None):
        """
        دفع العربون بكارت جديد (مثل self-drive)
        يتم استدعاؤها بعد confirm_booking
        """
        rental = self.get_object()
        
        # ===== BASIC VALIDATIONS (same as deposit_payment) =====
        
        # 1. Check if owner confirmed first and deposit is still required
        if rental.status == 'PendingOwnerConfirmation':
            return Response({
                'error_code': 'OWNER_CONFIRMATION_REQUIRED',
                'error_message': f'Owner must confirm booking first. Current status: {rental.status}'
            }, status=400)
        
        if rental.status == 'Confirmed':
            return Response({
                'error_code': 'DEPOSIT_ALREADY_PAID',
                'error_message': f'Deposit has already been paid. Current status: {rental.status}'
            }, status=400)
        
        if rental.status not in ['DepositRequired']:
            return Response({
                'error_code': 'INVALID_STATUS',
                'error_message': f'Cannot pay deposit in this status. Current status: {rental.status}'
            }, status=400)
        
        # 2. Check user is renter
        if rental.renter != request.user:
            return Response({
                'error_code': 'NOT_RENTER',
                'error_message': 'Only renter can pay deposit.'
            }, status=403)
        
        # 3. Check if already paid - get payment record
        from .models import RentalPayment
        try:
            payment = RentalPayment.objects.get(rental=rental)  # type: ignore
        except RentalPayment.DoesNotExist:  # type: ignore
            return Response({'error_code': 'PAYMENT_NOT_FOUND', 'error_message': 'لا يوجد بيانات دفع مرتبطة بهذا الحجز.'}, status=400)
        if not payment or not hasattr(rental, 'breakdown'):
            return Response({'error_code': 'PAYMENT_NOT_FOUND', 'error_message': 'لا يوجد بيانات دفع مرتبطة بهذا الحجز.'}, status=400)
        if not hasattr(payment, 'deposit_amount') or not payment.deposit_amount:
            payment.deposit_amount = rental.breakdown.deposit
            payment.save()
        required_cents = int(round(float(payment.deposit_amount) * 100))
        if not amount_cents or int(amount_cents) != required_cents:
            return Response({'error_code': 'INVALID_AMOUNT', 'error_message': f'المبلغ المطلوب للعربون هو {required_cents} قرش.'}, status=400)
        if payment.deposit_paid_status == 'Paid':
            return Response({'error_code': 'ALREADY_PAID', 'error_message': 'تم دفع العربون بالفعل.'}, status=400)
        if payment_method != 'new_card':
            return Response({'error_code': 'INVALID_METHOD', 'error_message': 'طريقة الدفع يجب أن تكون new_card.'}, status=400)
        try:
            from payments.services import paymob
            from django.conf import settings
            auth_token = paymob.get_auth_token()
            import uuid
            reference = str(uuid.uuid4())
            user_id = str(user.id)
            merchant_order_id_with_user = f"{reference}_{user_id}"
            order_id = paymob.create_order(auth_token, amount_cents, merchant_order_id_with_user)
            integration_id = settings.PAYMOB_INTEGRATION_ID_CARD
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
            payment_token = paymob.get_payment_token(
                auth_token, order_id, amount_cents, billing_data, integration_id
            )
            iframe_url = f"https://accept.paymob.com/api/acceptance/iframes/{settings.PAYMOB_IFRAME_ID}?payment_token={payment_token}"
            payment.deposit_transaction_id = order_id
            payment.save()
            return Response({
                'iframe_url': iframe_url,
                'order_id': order_id,
                'message': 'يرجى إكمال الدفع عبر الرابط'
            })
        except Exception as e:
            return Response({'error_code': 'PAYMOB_ERROR', 'error_message': str(e)}, status=500)

    def get(self, request, rental_id):
        user = request.user
        rental = get_object_or_404(Rental, id=rental_id)
        if rental.renter != user:
            return Response({'error_code': 'NOT_RENTER', 'error_message': 'يجب أن تكون المستأجر في هذا الحجز.'}, status=403)
        try:
            payment = RentalPayment.objects.get(rental=rental)  # type: ignore
        except RentalPayment.DoesNotExist:  # type: ignore
            return Response({'error_code': 'PAYMENT_NOT_FOUND', 'error_message': 'لا يوجد بيانات دفع مرتبطة بهذا الحجز.'}, status=400)
        from .serializers import RentalPaymentSerializer
        return Response({
            'deposit_paid_status': payment.deposit_paid_status,
            'deposit_paid_at': payment.deposit_paid_at,
            'deposit_transaction_id': payment.deposit_transaction_id,
            'payment': RentalPaymentSerializer(payment).data,
        })

    @action(detail=True, methods=['post'])
    def start_trip(self, request, pk=None):
        """
        بدء الرحلة مع دفع المبلغ المتبقي تلقائياً بالسيفد كارت
        """
        rental = self.get_object()
        
        # ===== BASIC VALIDATIONS =====
        
        # 1. التحقق من الصلاحيات - فقط مالك السيارة يمكنه بدء الرحلة
        if rental.car.owner != request.user:
            return Response({
                'error_code': 'NOT_OWNER',
                'error_message': 'Only the car owner can start the trip.',
                'required_role': 'car_owner'
            }, status=403)
        
        # 2. التحقق من الحالة - يجب أن تكون مؤكدة
        if rental.status == 'Ongoing':
            return Response({
                'status': 'Trip already started.',
                'message': 'This trip has already been started.',
                'trip_status': {
                    'current_status': rental.status,
                    'started_at': rental.updated_at.isoformat() if rental.updated_at else None
                },
                'info': 'Trip is currently in progress.'
            }, status=200)
        
        if rental.status == 'Finished':
            return Response({
                'status': 'Trip already finished.',
                'message': 'This trip has already been completed.',
                'trip_status': {
                    'current_status': rental.status,
                    'finished_at': rental.updated_at.isoformat() if rental.updated_at else None
                },
                'info': 'Trip has been completed and cannot be started again.'
            }, status=200)
        
        if rental.status == 'Canceled':
            return Response({
                'status': 'Trip canceled.',
                'message': 'This trip has been canceled.',
                'trip_status': {
                    'current_status': rental.status
                },
                'info': 'Canceled trips cannot be started.'
            }, status=200)
        
        if rental.status != 'Confirmed':
            return Response({
                'error_code': 'INVALID_STATUS',
                'error_message': 'Trip can only be started after deposit is paid and booking is confirmed.',
                'current_status': rental.status,
                'required_status': 'Confirmed',
                'next_actions': {
                    'PendingOwnerConfirmation': 'Wait for owner to confirm booking',
                    'DepositRequired': 'Renter must pay deposit first'
                }
            }, status=400)
        
        # 3. التحقق من تأكيد وصول المالك للبيك أب
        if not rental.owner_arrival_confirmed:
            return Response({
                'error_code': 'OWNER_ARRIVAL_REQUIRED',
                'error_message': 'Owner must confirm arrival at pickup location before starting the trip.',
                'required_action': 'owner_confirm_arrival',
                'pickup_address': rental.pickup_address,
                'endpoint': f'/api/rentals/{rental.id}/owner_confirm_arrival/'
            }, status=400)
        
        # 4. التحقق من أن المستأجر أعلن أنه في الطريق (اختياري ولكن مفضل)
        if not rental.renter_on_way_announced:
            return Response({
                'error_code': 'RENTER_NOT_ON_WAY',
                'error_message': 'Renter has not announced they are on the way yet.',
                'warning': 'You can still start the trip, but it\'s recommended to wait for renter confirmation.',
                'can_proceed': True,
                'endpoint': f'/api/rentals/{rental.id}/renter_on_way/'
            }, status=400)
        
        # ===== PAYMENT PROCESSING =====
        
        from .models import RentalPayment
        payment, _ = RentalPayment.objects.get_or_create(rental=rental)
        
        # التحقق من وجود breakdown وحساب المبلغ المتبقي
        if not hasattr(rental, 'breakdown'):
            return Response({
                'error_code': 'BREAKDOWN_NOT_FOUND',
                'error_message': 'Rental breakdown not found. Please calculate costs first.',
                'endpoint': f'/api/rentals/{rental.id}/calculate_costs/'
            }, status=400)
        
        # حساب المبلغ المتبقي
        remaining_amount = float(payment.remaining_amount or 0)
        if remaining_amount <= 0:
            return Response({
                'error_code': 'NO_REMAINING_AMOUNT',
                'error_message': 'No remaining amount to charge. Trip can be started without payment.',
                'remaining_amount': remaining_amount
            }, status=400)
        
        # ===== REAL PAYMENT PROCESSING =====
        
        payment_status = 'Pending'
        payment_message = ''
        transaction_id = None
        
        if rental.payment_method in ['visa', 'wallet']:
            # للدفع الإلكتروني - استخدم السيفد كارت
            if not rental.selected_card:
                return Response({
                    'error_code': 'NO_SELECTED_CARD',
                    'error_message': 'No selected card found for automatic payment.',
                    'payment_method': rental.payment_method,
                    'required_action': 'Select a card for automatic payments'
                }, status=400)
            
            try:
                # استخدام الدفع الحقيقي بالسيفد كارت
                from payments.services.payment_gateway import pay_with_saved_card_gateway
                
                amount_cents = int(round(remaining_amount * 100))
                result = pay_with_saved_card_gateway(
                    amount_cents=amount_cents,
                    user=rental.renter,
                    saved_card_token=rental.selected_card.token
                )
                
                if result['success']:
                    # نجح الدفع
                    payment.remaining_paid_status = 'Paid'
                    payment.remaining_paid_at = timezone.now()
                    payment.remaining_transaction_id = result['transaction_id']
                    payment.save()
                    
                    payment_status = 'Paid'
                    payment_message = f'Remaining amount {remaining_amount} EGP charged successfully via {rental.selected_card.card_brand} card.'
                    transaction_id = result['transaction_id']
                else:
                    # فشل الدفع
                    payment.remaining_paid_status = 'Failed'
                    payment.save()
                    
                    return Response({
                        'error_code': 'PAYMENT_FAILED',
                        'error_message': 'Payment for remaining amount failed.',
                        'payment_details': {
                            'method': rental.payment_method,
                            'card_brand': rental.selected_card.card_brand,
                            'card_last_four': rental.selected_card.card_last_four_digits,
                            'amount': remaining_amount,
                            'failure_reason': result.get('message', 'Unknown error')
                        },
                        'suggestions': [
                            'Check card balance',
                            'Verify card is still valid',
                            'Try with a different card'
                        ]
                    }, status=402)
                    
            except Exception as e:
                payment.remaining_paid_status = 'Failed'
                payment.save()
                
                return Response({
                    'error_code': 'PAYMENT_ERROR',
                    'error_message': f'Payment processing error: {str(e)}',
                    'payment_method': rental.payment_method,
                    'amount': remaining_amount
                }, status=500)
                
        else:
            # للدفع النقدي
            payment.remaining_paid_status = 'Pending'
            payment.save()
            payment_status = 'Pending'
            payment_message = f'Remaining amount {remaining_amount} EGP will be collected in cash at the end of trip.'
        
        # ===== TRIP START =====
        
        # تحديث حالة الحجز
        old_status = rental.status
        rental.status = 'Ongoing'
        rental.save()
        
        # تسجيل الحدث
        user = request.user if request.user.is_authenticated else None
        RentalLog.objects.create(
            rental=rental,
            event='Trip started',
            performed_by_type='Owner',
            performed_by=user
        )
        
        # إرسال إشعار للمستأجر
        from notifications.models import Notification
        Notification.objects.create(
            receiver=rental.renter,
            title="Trip Started",
            message=f"Your trip with {rental.car.brand} {rental.car.model} has started. Enjoy your ride!",
            notification_type="RENTAL",
            data={
                'rental_id': rental.id, 
                'payment_method': rental.payment_method,
                'payment_status': payment_status,
                'trip_started_at': timezone.now().isoformat()
            }
        )
        
        # ===== DETAILED RESPONSE =====
        
        return Response({
            'status': 'Trip started successfully.',
            'trip_details': {
                'rental_id': rental.id,
                'car_info': {
                    'brand': rental.car.brand,
                    'model': rental.car.model,
                    'plate_number': rental.car.plate_number,
                    'color': rental.car.color
                },
                'route_info': {
                    'pickup_address': rental.pickup_address,
                    'dropoff_address': rental.dropoff_address,
                    'start_date': rental.start_date,
                    'end_date': rental.end_date
                },
                'participants': {
                    'driver': {
                        'id': rental.car.owner.id,
                        'name': f"{rental.car.owner.first_name} {rental.car.owner.last_name}",
                        'phone': rental.car.owner.phone_number
                    },
                    'renter': {
                        'id': rental.renter.id,
                        'name': f"{rental.renter.first_name} {rental.renter.last_name}",
                        'phone': rental.renter.phone_number
                    }
                }
            },
            'payment_details': {
                'method': rental.payment_method,
                'status': payment_status,
                'remaining_amount': remaining_amount,
                'transaction_id': transaction_id,
                'card_info': {
                    'brand': rental.selected_card.card_brand if rental.selected_card else None,
                    'last_four': rental.selected_card.card_last_four_digits if rental.selected_card else None
                } if rental.payment_method in ['visa', 'wallet'] else None
            },
            'trip_status': {
                'old_status': old_status,
                'new_status': rental.status,
                'started_at': timezone.now().isoformat(),
                'owner_arrival_confirmed': rental.owner_arrival_confirmed,
                'renter_on_way_announced': rental.renter_on_way_announced
            },
            'message': payment_message,
            'next_actions': [
                'Use stop_arrival endpoint to confirm arrival at each stop',
                'Use end_waiting endpoint to end waiting at each stop',
                'Use end_trip endpoint when trip is finished'
            ]
        })

    @action(detail=True, methods=['post'])
    def stop_arrival(self, request, pk=None):
        """
        تأكيد وصول السائق للمحطة مع تفاصيل محترمة
        """
        rental = self.get_object()
        
        # ===== BASIC VALIDATIONS =====
        
        # 1. التحقق من الصلاحيات - فقط مالك السيارة
        if rental.car.owner != request.user:
            return Response({
                'error_code': 'NOT_OWNER',
                'error_message': 'Only the car owner can confirm stop arrivals.',
                'required_role': 'car_owner'
            }, status=403)
        
        # 2. التحقق من حالة الرحلة
        if rental.status != 'Ongoing':
            return Response({
                'error_code': 'INVALID_STATUS',
                'error_message': 'Stop arrivals can only be confirmed during ongoing trips.',
                'current_status': rental.status,
                'required_status': 'Ongoing'
            }, status=400)
        
        # 3. التحقق من وجود stop_order
        stop_order = request.data.get('stop_order')
        if stop_order is None:
            return Response({
                'error_code': 'MISSING_STOP_ORDER',
                'error_message': 'stop_order is required.',
                'required_parameter': 'stop_order'
            }, status=400)
        
        try:
            stop_order = int(stop_order)
        except (ValueError, TypeError):
            return Response({
                'error_code': 'INVALID_STOP_ORDER',
                'error_message': 'stop_order must be a valid integer.',
                'provided_value': request.data.get('stop_order')
            }, status=400)
        
        # 4. البحث عن المحطة
        try:
            stop = PlannedTripStop.objects.get(
                stop_order=stop_order, 
                planned_trip__rental_id=pk
            )
        except PlannedTripStop.DoesNotExist:
            return Response({
                'error_code': 'STOP_NOT_FOUND',
                'error_message': f'Stop #{stop_order} not found for this rental.',
                'available_stops': list(PlannedTripStop.objects.filter(
                    planned_trip__rental_id=pk
                ).values_list('stop_order', flat=True))
            }, status=404)
        
        # 5. التحقق من أن الرحلة بدأت
        from .models import RentalLog
        trip_started = RentalLog.objects.filter(
            rental_id=pk, 
            event__icontains='Trip started'
        ).exists()  # type: ignore
        
        if not trip_started:
            return Response({
                'error_code': 'TRIP_NOT_STARTED',
                'error_message': 'You must start the trip before confirming stop arrivals.',
                'required_action': 'start_trip',
                'endpoint': f'/api/rentals/{pk}/start_trip/'
            }, status=400)
        
        # 6. منع تكرار تسجيل الوصول لنفس المحطة
        if stop.waiting_started_at:
            return Response({
                'error_code': 'STOP_ALREADY_ARRIVED',
                'error_message': f'Arrival for stop #{stop_order} has already been confirmed.',
                'stop_details': {
                    'stop_order': stop.stop_order,
                    'address': stop.address,
                    'arrived_at': stop.waiting_started_at.isoformat() if hasattr(stop.waiting_started_at, 'isoformat') else str(stop.waiting_started_at) if stop.waiting_started_at else None
                }
            }, status=400)
        
        # 7. التحقق من منطق تسلسل المحطات
        if stop_order > 1:
            prev_stop = PlannedTripStop.objects.filter(
                planned_trip__rental_id=pk, 
                stop_order=stop_order-1
            ).first()  # type: ignore
            
            if prev_stop and not prev_stop.waiting_ended_at:
                return Response({
                    'error_code': 'PREVIOUS_STOP_NOT_ENDED',
                    'error_message': f'You must end waiting for stop #{stop_order-1} before starting stop #{stop_order}.',
                    'previous_stop': {
                        'stop_order': prev_stop.stop_order,
                        'address': prev_stop.address,
                        'waiting_started_at': prev_stop.waiting_started_at.isoformat() if hasattr(prev_stop.waiting_started_at, 'isoformat') else str(prev_stop.waiting_started_at) if prev_stop.waiting_started_at else None
                    },
                    'required_action': 'end_waiting',
                    'endpoint': f'/api/rentals/{pk}/end_waiting/'
                }, status=400)
        
        # ===== STOP ARRIVAL CONFIRMATION =====
        
        # تحديث المحطة
        stop.location_verified = True
        stop.waiting_started_at = request.data.get('waiting_started_at') or timezone.now()
        stop.save()
        
        # تسجيل الحدث
        RentalLog.objects.create(  # type: ignore
                rental=stop.planned_trip.rental,
                event=f'Stop arrival confirmed (Stop #{stop.stop_order})',
                performed_by_type='Owner',
                performed_by=request.user
            )
        
        # إرسال إشعار للمستأجر
        from notifications.models import Notification
        Notification.objects.create(
            receiver=rental.renter,
            title=f"Arrived at Stop #{stop_order}",
            message=f"Your driver has arrived at stop #{stop_order}: {stop.address}",
            notification_type="RENTAL",
            data={
                'rental_id': rental.id,
                'stop_order': stop_order,
                'stop_address': stop.address,
                'arrived_at': stop.waiting_started_at.isoformat() if hasattr(stop.waiting_started_at, 'isoformat') else str(stop.waiting_started_at) if stop.waiting_started_at else None
            }
        )
        
        # ===== DETAILED RESPONSE =====
        
        return Response({
            'status': 'Stop arrival confirmed successfully.',
            'stop_details': {
                'stop_order': stop.stop_order,
                'address': stop.address,
                'latitude': float(stop.latitude),
                'longitude': float(stop.longitude),
                'arrived_at': stop.waiting_started_at.isoformat() if hasattr(stop.waiting_started_at, 'isoformat') else str(stop.waiting_started_at) if stop.waiting_started_at else None,
                'location_verified': stop.location_verified
            },
            'trip_progress': {
                'current_stop': stop_order,
                'total_stops': PlannedTripStop.objects.filter(planned_trip__rental_id=pk).count(),
                'next_action': 'end_waiting',
                'endpoint': f'/api/rentals/{pk}/end_waiting/',
                'next_stop': self._get_next_stop_info(pk, stop_order)
            },
            'message': f'Successfully arrived at stop #{stop_order}: {stop.address}',
            'next_actions': [
                'Use end_waiting endpoint when ready to leave this stop',
                'Use stop_arrival endpoint for next stop when ready'
            ]
        })

    @action(detail=True, methods=['post'])
    def end_waiting(self, request, pk=None):
        """
        إنهاء الانتظار في محطة معينة مع تفاصيل محترمة
        """
        rental = self.get_object()
        
        # ===== BASIC VALIDATIONS =====
        
        # 1. التحقق من الصلاحيات - فقط مالك السيارة
        if rental.car.owner != request.user:
            return Response({
                'error_code': 'NOT_OWNER',
                'error_message': 'Only the car owner can end waiting at stops.',
                'required_role': 'car_owner'
            }, status=403)
        
        # 2. التحقق من حالة الرحلة
        if rental.status != 'Ongoing':
            return Response({
                'error_code': 'INVALID_STATUS',
                'error_message': 'Waiting can only be ended during ongoing trips.',
                'current_status': rental.status,
                'required_status': 'Ongoing'
            }, status=400)
        
        # 3. التحقق من وجود stop_order
        stop_order = request.data.get('stop_order')
        if stop_order is None:
            return Response({
                'error_code': 'MISSING_STOP_ORDER',
                'error_message': 'stop_order is required.',
                'required_parameter': 'stop_order'
            }, status=400)
        
        try:
            stop_order = int(stop_order)
        except (ValueError, TypeError):
            return Response({
                'error_code': 'INVALID_STOP_ORDER',
                'error_message': 'stop_order must be a valid integer.',
                'provided_value': request.data.get('stop_order')
            }, status=400)
        
        # 4. البحث عن المحطة
        try:
            stop = PlannedTripStop.objects.get(
                stop_order=stop_order, 
                planned_trip__rental_id=pk
            )
        except PlannedTripStop.DoesNotExist:
            return Response({
                'error_code': 'STOP_NOT_FOUND',
                'error_message': f'Stop #{stop_order} not found for this rental.',
                'available_stops': list(PlannedTripStop.objects.filter(
                    planned_trip__rental_id=pk
                ).values_list('stop_order', flat=True))
            }, status=404)
        
        # 5. التحقق من أن الانتظار بدأ فعلاً
        if not stop.waiting_started_at:
            return Response({
                'error_code': 'WAITING_NOT_STARTED',
                'error_message': f'You must start waiting at stop #{stop_order} before you can end it.',
                'stop_details': {
                    'stop_order': stop.stop_order,
                    'address': stop.address,
                    'waiting_started_at': stop.waiting_started_at
                },
                'required_action': 'stop_arrival',
                'endpoint': f'/api/rentals/{pk}/stop_arrival/'
            }, status=400)
        
        # 6. منع تكرار إنهاء الانتظار لنفس المحطة
        if stop.waiting_ended_at:
            return Response({
                'error_code': 'WAITING_ALREADY_ENDED',
                'error_message': f'Waiting for stop #{stop_order} has already been ended.',
                'stop_details': {
                    'stop_order': stop.stop_order,
                    'address': stop.address,
                    'waiting_ended_at': stop.waiting_ended_at.isoformat() if hasattr(stop.waiting_ended_at, 'isoformat') else str(stop.waiting_ended_at) if stop.waiting_ended_at else None,
                    'actual_waiting_minutes': stop.actual_waiting_minutes
                }
            }, status=400)
        
        # 7. التحقق من actual_waiting_minutes
        actual_waiting_minutes = request.data.get('actual_waiting_minutes', 0)
        try:
            actual_waiting_minutes = int(actual_waiting_minutes)
            if actual_waiting_minutes < 0:
                raise ValueError("Cannot be negative")
        except (ValueError, TypeError):
            return Response({
                'error_code': 'INVALID_WAITING_MINUTES',
                'error_message': 'actual_waiting_minutes must be a non-negative integer.',
                'provided_value': request.data.get('actual_waiting_minutes')
            }, status=400)
        
        # ===== END WAITING =====
        
        # تحديث المحطة
        stop.waiting_ended_at = request.data.get('waiting_ended_at') or timezone.now()
        stop.actual_waiting_minutes = actual_waiting_minutes
        stop.save()
        
        # حساب الوقت المخطط vs الفعلي
        planned_waiting = stop.approx_waiting_time_minutes
        waiting_difference = actual_waiting_minutes - planned_waiting
        
        # تسجيل الحدث
        RentalLog.objects.create(  # type: ignore
            rental=stop.planned_trip.rental,
            event=f'Waiting ended at stop #{stop.stop_order} (actual_waiting_minutes={actual_waiting_minutes})',
            performed_by_type='Owner',
            performed_by=request.user
        )
        
        # إرسال إشعار للمستأجر
        from notifications.models import Notification
        Notification.objects.create(
            receiver=rental.renter,
            title=f"Left Stop #{stop_order}",
            message=f"Your driver has left stop #{stop_order}: {stop.address}",
            notification_type="RENTAL",
            data={
                'rental_id': rental.id,
                'stop_order': stop_order,
                'stop_address': stop.address,
                'left_at': stop.waiting_ended_at.isoformat() if hasattr(stop.waiting_ended_at, 'isoformat') else str(stop.waiting_ended_at) if stop.waiting_ended_at else None,
                'waiting_time': actual_waiting_minutes
            }
        )
        
        # ===== DETAILED RESPONSE =====
        
        return Response({
            'status': 'Waiting ended successfully.',
            'stop_details': {
                'stop_order': stop.stop_order,
                'address': stop.address,
                'waiting_started_at': stop.waiting_started_at.isoformat() if hasattr(stop.waiting_started_at, 'isoformat') else str(stop.waiting_started_at) if stop.waiting_started_at else None,
                'waiting_ended_at': stop.waiting_ended_at.isoformat() if hasattr(stop.waiting_ended_at, 'isoformat') else str(stop.waiting_ended_at) if stop.waiting_ended_at else None,
                'planned_waiting_minutes': planned_waiting,
                'actual_waiting_minutes': actual_waiting_minutes,
                'waiting_difference': waiting_difference,
                'is_over_time': waiting_difference > 0
            },
            'trip_progress': {
                'current_stop': stop_order,
                'total_stops': PlannedTripStop.objects.filter(planned_trip__rental_id=pk).count(),
                'next_stop': self._get_next_stop_info(pk, stop_order)
            },
            'message': f'Successfully left stop #{stop_order}: {stop.address} after {actual_waiting_minutes} minutes',
            'next_actions': [
                'Use stop_arrival endpoint for next stop when ready',
                'Use end_trip endpoint if this was the last stop'
            ]
        })

    @action(detail=True, methods=['post'])
    def end_trip(self, request, pk=None):
        """
        إنهاء الرحلة وحساب الزيادات (زي self-drive) مع تفاصيل محترمة
        """
        rental = self.get_object()
        if rental.status != 'Ongoing':
            return Response({
                'error_code': 'INVALID_STATUS',
                'error_message': 'لا يمكن إنهاء الرحلة إلا إذا كانت الحالة جارية.',
                'details': {
                    'rental_id': rental.id,
                    'current_status': rental.status,
                    'required_status': 'Ongoing'
                }
            }, status=400)
        
        from .models import RentalPayment, PlannedTripStop
        payment, _ = RentalPayment.objects.get_or_create(rental=rental)
        planned_stops = PlannedTripStop.objects.filter(planned_trip__rental_id=rental.id)
        
        # تحقق من إنهاء الانتظار في آخر محطة
        if planned_stops.exists():
            last_stop = planned_stops.order_by('-stop_order').first()
            if not last_stop.waiting_ended_at:
                return Response({
                    'error_code': 'WAITING_NOT_ENDED',
                    'error_message': 'يجب إنهاء الانتظار في آخر محطة قبل إنهاء الرحلة.',
                    'details': {
                        'rental_id': rental.id,
                        'last_stop_order': last_stop.stop_order,
                        'last_stop_address': last_stop.address
                    }
                }, status=400)
        
        # حساب الزيادات (زي self-drive)
        actual_total_waiting_minutes = 0
        planned_total_waiting_minutes = 0
        
        for stop in planned_stops:
            # التأكد من أن القيم صحيحة
            actual_minutes = getattr(stop, 'actual_waiting_minutes', 0) or 0
            planned_minutes = getattr(stop, 'approx_waiting_time_minutes', 0) or 0
            
            actual_total_waiting_minutes += int(float(actual_minutes))
            planned_total_waiting_minutes += int(float(planned_minutes))
        
        extra_waiting_minutes = max(0, actual_total_waiting_minutes - planned_total_waiting_minutes)
        
        car = rental.car
        extra_hour_cost = float(car.usage_policy.extra_hour_cost or 0)
        excess_amount = extra_waiting_minutes * (extra_hour_cost / 60)
        
        # التكلفة النهائية = التكلفة الأصلية + الزيادات
        base_final_cost = float(rental.breakdown.final_cost)
        final_amount = base_final_cost + excess_amount
        
        # تحديث breakdown بتفاصيل الزيادات (واضح ومنظم)
        breakdown = rental.breakdown
        breakdown.actual_total_waiting_minutes = actual_total_waiting_minutes
        breakdown.extra_waiting_minutes = extra_waiting_minutes
        breakdown.excess_waiting_cost = excess_amount
        breakdown.final_total_cost = final_amount
        breakdown.save()
        
        # تحديث بيانات الدفع
        payment.excess_amount = excess_amount
        payment.rental_total_amount = final_amount
        payment.save()
        
        # ===== دفع الزيادة إذا وجدت =====
        payment_status = 'No_Excess'
        payment_message = ''
        transaction_id = None
        
        if excess_amount > 0:
            # هناك مبلغ زائد يجب دفعه
            if rental.payment_method in ['visa', 'wallet'] and rental.selected_card:
                try:
                    # استخدام الدفع الحقيقي بالسيفد كارت
                    from payments.services.payment_gateway import pay_with_saved_card_gateway
                    
                    amount_cents = int(round(excess_amount * 100))
                    result = pay_with_saved_card_gateway(
                        amount_cents=amount_cents,
                        user=rental.renter,
                        saved_card_token=rental.selected_card.token
                    )
                    
                    if result['success']:
                        # نجح دفع الزيادة
                        payment.excess_paid_status = 'Paid'
                        payment.excess_paid_at = timezone.now()
                        payment.excess_transaction_id = result['transaction_id']
                        payment.save()
                        
                        payment_status = 'Excess_Paid'
                        payment_message = f'Excess amount {excess_amount} EGP charged successfully via {rental.selected_card.card_brand} card.'
                        transaction_id = result['transaction_id']
                    else:
                        # فشل دفع الزيادة
                        payment.excess_paid_status = 'Failed'
                        payment.save()
                        
                        payment_status = 'Excess_Failed'
                        payment_message = f'Failed to charge excess amount: {result.get("message", "Unknown error")}'
                        
                except Exception as e:
                    payment.excess_paid_status = 'Failed'
                    payment.save()
                    
                    payment_status = 'Excess_Error'
                    payment_message = f'Error processing excess payment: {str(e)}'
            else:
                # للدفع النقدي
                payment.excess_paid_status = 'Pending'
                payment.save()
                payment_status = 'Excess_Pending'
                payment_message = f'Excess amount {excess_amount} EGP will be collected in cash.'
        else:
            payment_message = 'No excess amount to charge.'
        
        # تحديث حالة الرحلة
        old_status = rental.status
        rental.status = 'Finished'
        rental.save()
        
        # تسجيل الحدث
        from .models import RentalLog
        RentalLog.objects.create(
            rental=rental,
            event='Trip ended',
            performed_by_type='Owner',
            performed_by=request.user
        )
        
        # إرسال إشعار للمستأجر
        from notifications.models import Notification
        Notification.objects.create(
            receiver=rental.renter,
            title="Trip Ended",
            message=f"Your trip with {rental.car.brand} {rental.car.model} has ended. Thank you for using our service!",
            notification_type="RENTAL",
            data={
                'rental_id': rental.id,
                'final_amount': final_amount,
                'excess_amount': excess_amount,
                'trip_ended_at': timezone.now().isoformat()
            }
        )
        
        # ===== RESPONSE =====
        
        # ===== معالجة تلقائية للـ payout =====
        payout_processed = False
        payout_response = None
        
        try:
            # استدعاء دالة payout تلقائياً
            from django.test import RequestFactory
            from django.contrib.auth.models import AnonymousUser
            
            # إنشاء request مصطنع للـ payout
            factory = RequestFactory()
            payout_request = factory.post(f'/api/rentals/{rental.id}/payout/')
            payout_request.user = request.user
            
            # استدعاء دالة payout
            payout_response = self.payout(payout_request, pk=rental.id)
            payout_processed = payout_response.status_code == 200
            
        except Exception as e:
            payout_processed = False
            payout_error = str(e)
        
        return Response({
            'status': 'Trip ended successfully.',
            'trip_details': {
                'rental_id': rental.id,
                'old_status': old_status,
                'new_status': rental.status,
                'ended_at': timezone.now().isoformat(),
                'car_info': {
                    'brand': rental.car.brand,
                    'model': rental.car.model,
                    'plate_number': rental.car.plate_number
                }
            },
            'financial_summary': {
                'base_cost': base_final_cost,
                'excess_amount': excess_amount,
                'final_total_cost': final_amount,
                'waiting_details': {
                    'planned_waiting_minutes': planned_total_waiting_minutes,
                    'actual_waiting_minutes': actual_total_waiting_minutes,
                    'extra_waiting_minutes': extra_waiting_minutes,
                    'extra_hour_cost': extra_hour_cost
                }
            },
            'payment_status': {
                'deposit_paid': payment.deposit_paid_status == 'Paid',
                'remaining_paid': payment.remaining_paid_status == 'Paid',
                'excess_paid': getattr(payment, 'excess_paid_status', 'Not_Applicable'),
                'excess_amount': excess_amount,
                'total_amount': final_amount,
                'payment_status': payment_status,
                'transaction_id': transaction_id
            },
            'payout_processing': {
                'processed_automatically': payout_processed,
                'payout_response': payout_response.data if payout_response else None,
                'payout_error': payout_error if not payout_processed else None,
                'wallet_operations': payout_response.data.get('wallet_operations') if payout_response and payout_response.data else None
            },
            'message': f'Trip ended successfully. {payment_message} Final amount: {final_amount} EGP (Base: {base_final_cost} + Excess: {excess_amount})',
            'next_actions': [
                'Payout processed automatically' if payout_processed else 'Manual payout required',
                'Trip is now fully completed' if payout_processed else 'Process payout manually'
            ]
        })
    
    @action(detail=True, methods=['post'])
    def renter_on_way(self, request, pk=None):
        """
        المستأجر يعلن أنه في طريقه للقاء السائق
        """
        rental = self.get_object()
        
        # ===== VALIDATIONS =====
        
        # 1. Check if user is the renter
        if rental.renter != request.user:
            return Response({
                'error_code': 'NOT_RENTER',
                'error_message': 'فقط المستأجر يمكنه إعلان أنه في الطريق.',
                'details': {
                    'rental_id': rental.id,
                    'renter_id': rental.renter.id,
                    'current_user': request.user.id
                }
            }, status=403)
        
        # 2. Check rental status
        if rental.status not in ['Confirmed', 'DepositRequired']:
            return Response({
                'error_code': 'INVALID_STATUS',
                'error_message': f'يمكن إعلان الوصول فقط عندما يكون الحجز مؤكداً. الحالة الحالية: {rental.status}',
                'details': {
                    'rental_id': rental.id,
                    'current_status': rental.status,
                    'allowed_statuses': ['Confirmed', 'DepositRequired']
                }
            }, status=400)
        
        # 3. Check if driver has confirmed arrival first
        if not rental.owner_arrival_confirmed:
            return Response({
                'error_code': 'DRIVER_NOT_ARRIVED',
                'error_message': 'يجب أن يؤكد السائق وصوله لموقع الاستلام أولاً قبل إعلانك أنك في الطريق.',
                'details': {
                    'rental_id': rental.id,
                    'driver_arrival_status': 'pending',
                    'pickup_address': rental.pickup_address
                }
            }, status=400)
        
        # 4. Check if already announced
        if hasattr(rental, 'renter_on_way_announced') and rental.renter_on_way_announced:
            return Response({
                'error_code': 'ALREADY_ANNOUNCED',
                'error_message': 'لقد أعلنت بالفعل أنك في الطريق.',
                'details': {
                    'rental_id': rental.id,
                    'announced_at': getattr(rental, 'renter_on_way_announced_at', None),
                    'pickup_address': rental.pickup_address
                }
            }, status=400)
        
        # ===== PROCESSING =====
        
        # Update rental with on-way announcement
        rental.renter_on_way_announced = True
        rental.renter_on_way_announced_at = timezone.now()
        rental.save()
        
        # Log the event
        RentalLog.objects.create(
            rental=rental,
            event='Renter announced they are on the way',
            performed_by_type='Renter',
            performed_by=request.user
        )
        
        # Send notification to driver
        from notifications.models import Notification
        Notification.objects.create(
            receiver=rental.car.owner,
            title="المستأجر في الطريق",
            message=f"المستأجر في طريقه إلى {rental.pickup_address}. يرجى الاستعداد.",
            notification_type="RENTAL",
            data={
                'rental_id': rental.id,
                'pickup_address': rental.pickup_address,
                'event': 'renter_on_way'
            }
        )
        
        # ===== RESPONSE =====
        
        return Response({
            'status': 'success',
            'message': 'تم إعلان أنك في الطريق بنجاح.',
            'details': {
                'rental_id': rental.id,
                'announced_at': rental.renter_on_way_announced_at,
                'pickup_address': rental.pickup_address,
                'car_details': {
                    'brand': rental.car.brand,
                    'model': rental.car.model,
                    'year': rental.car.year
                },
                'driver_info': {
                    'name': rental.car.owner.get_full_name() or rental.car.owner.email,
                    'phone': rental.car.owner.phone_number
                }
            },
            'next_actions': [
                'Driver has been notified',
                'Trip can be started when you arrive at pickup location'
            ],
            'trip_progress': {
                'current_step': 'Renter On Way',
                'completed_steps': [
                    'Rental Created',
                    'Owner Confirmed Booking',
                    'Deposit Paid',
                    'Owner Arrival Confirmed',
                    'Renter On Way'
                ],
                'remaining_steps': [
                    'Start Trip',
                    'Trip Stops',
                    'End Trip'
                ]
            }
        })

    @action(detail=True, methods=['post'])
    def payout(self, request, pk=None):
        """
        معالجة تلقائية لجميع المدفوعات والأرباح عند إنهاء الرحلة:
        - تحويل أرباح السائق لمحفظته (فيزا)
        - خصم عمولة المنصة من محفظة السائق (كاش)
        - تحديث إحصائيات المستخدمين
        - إرسال إشعارات للطرفين
        - تسجيل جميع العمليات
        """
        rental = self.get_object()
        
        # ===== VALIDATIONS =====
        
        # 1. التحقق من حالة الرحلة
        if rental.status != 'Finished':
            return Response({
                'error_code': 'INVALID_STATUS',
                'error_message': 'Payout can only be processed after trip is finished.',
                'current_status': rental.status,
                'required_status': 'Finished'
            }, status=400)
        
        # 2. التحقق من الصلاحيات - فقط مالك السيارة
        if rental.car.owner != request.user:
            return Response({
                'error_code': 'NOT_OWNER',
                'error_message': 'Only the car owner can process payout.',
                'required_role': 'car_owner'
            }, status=403)
        
        # 3. التحقق من عدم معالجة الدفع مسبقاً
        from .models import RentalPayment
        try:
            payment = RentalPayment.objects.get(rental=rental)
            if getattr(payment, 'payout_processed', False):
                return Response({
                    'error_code': 'ALREADY_PROCESSED',
                    'error_message': 'Payout has already been processed for this rental.',
                    'processed_at': getattr(payment, 'payout_processed_at', None)
                }, status=400)
        except RentalPayment.DoesNotExist:
            return Response({
                'error_code': 'PAYMENT_NOT_FOUND',
                'error_message': 'Payment record not found for this rental.'
            }, status=400)
        
        # ===== PROCESSING =====
        
        breakdown = getattr(rental, 'breakdown', None)
        if not breakdown:
            return Response({
                'error_code': 'BREAKDOWN_NOT_FOUND',
                'error_message': 'Rental breakdown not found.'
            }, status=400)
        
        # حساب المبالغ على السعر النهائي (بعد الزيادات)
        total_amount = float(breakdown.final_total_cost or breakdown.final_cost or 0)
        excess_amount = float(payment.excess_amount or 0)
        
        # إعادة حساب الأرباح والعمولة على السعر النهائي
        commission_rate = 0.1  # 10% عمولة المنصة
        platform_fee = total_amount * commission_rate
        driver_earnings = total_amount - platform_fee
        
        # تحديث breakdown بالقيم الجديدة
        breakdown.driver_earnings = driver_earnings
        breakdown.platform_fee = platform_fee
        breakdown.save()
        
        payout_results = {
            'driver_earnings_transferred': False,
            'platform_fee_deducted': False,
            'driver_earnings_amount': driver_earnings,
            'platform_fee_amount': platform_fee,
            'total_amount': total_amount,
            'excess_amount': excess_amount,
            'wallet_operations': []
        }
        
        # ===== 1. تحويل أرباح السائق (فيزا) =====
        
        if rental.payment_method in ['visa', 'wallet'] and driver_earnings > 0:
            try:
                # تحويل أرباح السائق لمحفظته
                from wallets.models import Wallet, WalletTransaction
                from wallets.services import WalletService
                driver_wallet, created = Wallet.objects.get_or_create(user=rental.car.owner)
                balance_before = float(driver_wallet.balance or 0)
                transaction_result = WalletService.add_funds_to_wallet(
                    user=rental.car.owner,
                    amount=driver_earnings,
                    transaction_type_name='DRIVER_EARNINGS',
                    description=f'Driver earnings from rental #{rental.id}',
                    reference_id=str(rental.id),
                    reference_type='RENTAL'
                )
                driver_wallet.refresh_from_db()
                balance_after = float(driver_wallet.balance or 0)
                if transaction_result:
                    payout_results['driver_earnings_transferred'] = True
                    payout_results['driver_wallet_transaction_id'] = str(transaction_result.id)
                    wallet_operation = {
                        'operation_type': 'ADD_MONEY',
                        'wallet_owner': 'Driver',
                        'amount': driver_earnings,
                        'transaction_id': str(transaction_result.id),
                        'description': f'Driver earnings from rental #{rental.id}',
                        'wallet_balance_before': balance_before,
                        'wallet_balance_after': balance_after,
                        'status': 'SUCCESS',
                        'timestamp': timezone.now().isoformat()
                    }
                    payout_results['wallet_operations'].append(wallet_operation)
                    RentalLog.objects.create(
                        rental=rental,
                        event=f'Driver earnings {driver_earnings} EGP transferred to wallet',
                        performed_by_type='System',
                        performed_by=request.user
                    )
                else:
                    payout_results['driver_earnings_error'] = 'Failed to add funds to wallet'
                    wallet_operation = {
                        'operation_type': 'ADD_MONEY',
                        'wallet_owner': 'Driver',
                        'amount': driver_earnings,
                        'transaction_id': None,
                        'description': f'Driver earnings from rental #{rental.id}',
                        'status': 'FAILED',
                        'error_message': 'Failed to add funds to wallet',
                        'timestamp': timezone.now().isoformat()
                    }
                    payout_results['wallet_operations'].append(wallet_operation)
            except Exception as e:
                payout_results['driver_earnings_error'] = str(e)
                wallet_operation = {
                    'operation_type': 'ADD_MONEY',
                    'wallet_owner': 'Driver',
                    'amount': driver_earnings,
                    'transaction_id': None,
                    'description': f'Driver earnings from rental #{rental.id}',
                    'status': 'FAILED',
                    'error_message': str(e),
                    'timestamp': timezone.now().isoformat()
                }
                payout_results['wallet_operations'].append(wallet_operation)

        # ===== 2. خصم عمولة المنصة (كاش) =====
        
        if rental.payment_method == 'cash' and platform_fee > 0:
            try:
                from wallets.models import Wallet
                from wallets.services import WalletService
                driver_wallet, created = Wallet.objects.get_or_create(user=rental.car.owner)
                balance_before = float(driver_wallet.balance or 0)
                transaction_result = WalletService.deduct_funds_from_wallet(
                    user=rental.car.owner,
                    amount=platform_fee,
                    transaction_type_name='PLATFORM_FEE',
                    description=f'Platform fee for rental #{rental.id}',
                    reference_id=str(rental.id),
                    reference_type='RENTAL'
                )
                driver_wallet.refresh_from_db()
                balance_after = float(driver_wallet.balance or 0)
                if transaction_result:
                    payout_results['platform_fee_deducted'] = True
                    payout_results['platform_fee_transaction_id'] = str(transaction_result.id)
                    wallet_operation = {
                        'operation_type': 'DEDUCT_MONEY',
                        'wallet_owner': 'Driver',
                        'amount': platform_fee,
                        'transaction_id': str(transaction_result.id),
                        'description': f'Platform fee for rental #{rental.id}',
                        'wallet_balance_before': balance_before,
                        'wallet_balance_after': balance_after,
                        'status': 'SUCCESS',
                        'timestamp': timezone.now().isoformat()
                    }
                    payout_results['wallet_operations'].append(wallet_operation)
                    RentalLog.objects.create(
                        rental=rental,
                        event=f'Platform fee {platform_fee} EGP deducted from driver wallet',
                        performed_by_type='System',
                        performed_by=request.user
                    )
                else:
                    payout_results['platform_fee_error'] = 'Failed to deduct funds from wallet'
                    wallet_operation = {
                        'operation_type': 'DEDUCT_MONEY',
                        'wallet_owner': 'Driver',
                        'amount': platform_fee,
                        'transaction_id': None,
                        'description': f'Platform fee for rental #{rental.id}',
                        'status': 'FAILED',
                        'error_message': 'Failed to deduct funds from wallet',
                        'timestamp': timezone.now().isoformat()
                    }
                    payout_results['wallet_operations'].append(wallet_operation)
            except Exception as e:
                payout_results['platform_fee_error'] = str(e)
                wallet_operation = {
                    'operation_type': 'DEDUCT_MONEY',
                    'wallet_owner': 'Driver',
                    'amount': platform_fee,
                    'transaction_id': None,
                    'description': f'Platform fee for rental #{rental.id}',
                    'status': 'FAILED',
                    'error_message': str(e),
                    'timestamp': timezone.now().isoformat()
                }
                payout_results['wallet_operations'].append(wallet_operation)
        
        # ===== 3. تحديث إحصائيات المستخدمين =====
        
        try:
            # تحديث إحصائيات السائق
            driver = rental.car.owner
            driver.total_earnings = float(getattr(driver, 'total_earnings', 0)) + driver_earnings
            driver.completed_trips = int(getattr(driver, 'completed_trips', 0)) + 1
            driver.save()
            
            # تحديث إحصائيات المستأجر
            renter = rental.renter
            renter.completed_trips = int(getattr(renter, 'completed_trips', 0)) + 1
            renter.total_spent = float(getattr(renter, 'total_spent', 0)) + total_amount
            renter.save()
            
            payout_results['statistics_updated'] = True
            
        except Exception as e:
            payout_results['statistics_error'] = str(e)
        
        # ===== 4. تحديث حالة الدفع =====
        
        payment.payout_processed = True
        payment.payout_processed_at = timezone.now()
        payment.driver_earnings_transferred = payout_results['driver_earnings_transferred']
        payment.platform_fee_deducted = payout_results['platform_fee_deducted']
        payment.save()
        
        # ===== 5. تسجيل الحدث الرئيسي =====
        
        RentalLog.objects.create(
            rental=rental,
            event='Payout processed successfully',
            performed_by_type='Owner',
            performed_by=request.user
        )
        
        # ===== 6. إرسال إشعارات =====
        
        try:
            from notifications.models import Notification
            
            # إشعار للسائق
            Notification.objects.create(
                receiver=rental.car.owner,
                title="Payout Processed",
                message=f"Your earnings of {driver_earnings} EGP have been transferred to your wallet for rental #{rental.id}.",
                notification_type="PAYMENT",
                data={
                    'rental_id': rental.id,
                    'earnings_amount': driver_earnings,
                    'platform_fee': platform_fee,
                    'event': 'payout_processed'
                }
            )
            
            # إشعار للمستأجر
            Notification.objects.create(
                receiver=rental.renter,
                title="Trip Completed",
                message=f"Your trip with {rental.car.brand} {rental.car.model} has been completed and all payments processed.",
                notification_type="RENTAL",
                data={
                    'rental_id': rental.id,
                    'total_amount': total_amount,
                    'event': 'trip_completed'
                }
            )
            
            payout_results['notifications_sent'] = True
            
        except Exception as e:
            payout_results['notifications_error'] = str(e)
        
        # ===== 7. تحديث حالة الرحلة =====
        
        rental.status = 'Completed'
        rental.save()
        
        # ===== RESPONSE =====
        
        return Response({
            'status': 'Payout processed successfully.',
            'payout_summary': {
                'rental_id': rental.id,
                'driver_earnings': driver_earnings,
                'platform_fee': platform_fee,
                'total_amount': total_amount,
                'excess_amount': excess_amount,
                'payment_method': rental.payment_method
            },
            'processing_results': {
                'driver_earnings_transferred': payout_results['driver_earnings_transferred'],
                'platform_fee_deducted': payout_results['platform_fee_deducted'],
                'statistics_updated': payout_results.get('statistics_updated', False),
                'notifications_sent': payout_results.get('notifications_sent', False)
            },
            'transaction_details': {
                'driver_wallet_transaction_id': payout_results.get('driver_wallet_transaction_id'),
                'platform_fee_transaction_id': payout_results.get('platform_fee_transaction_id'),
                'payout_processed_at': payment.payout_processed_at.isoformat()
            },
            'wallet_operations': {
                'total_operations': len(payout_results['wallet_operations']),
                'successful_operations': len([op for op in payout_results['wallet_operations'] if op['status'] == 'SUCCESS']),
                'failed_operations': len([op for op in payout_results['wallet_operations'] if op['status'] == 'FAILED']),
                'operations_details': payout_results['wallet_operations']
            },
            'errors': {
                'driver_earnings_error': payout_results.get('driver_earnings_error'),
                'platform_fee_error': payout_results.get('platform_fee_error'),
                'statistics_error': payout_results.get('statistics_error'),
                'notifications_error': payout_results.get('notifications_error')
            },
            'message': f'Payout processed successfully. Driver earnings: {driver_earnings} EGP, Platform fee: {platform_fee} EGP',
            'next_actions': [
                'Trip is now fully completed',
                'All financial transactions processed',
                'Statistics updated for both users'
            ]
        })

    def _get_next_stop_info(self, rental_id, current_stop_order):
        """دالة مساعدة للحصول على معلومات المحطة التالية"""
        try:
            next_stop = PlannedTripStop.objects.filter(  # type: ignore
                planned_trip__rental_id=rental_id,
                stop_order=current_stop_order + 1
            ).first()
            
            if next_stop:
                return {
                    'stop_order': next_stop.stop_order,
                    'address': next_stop.address,
                    'latitude': float(next_stop.latitude),
                    'longitude': float(next_stop.longitude),
                    'approx_waiting_time_minutes': next_stop.approx_waiting_time_minutes,
                    'endpoint': f'/api/rentals/{rental_id}/stop_arrival/'
                }
            else:
                return {
                    'message': 'This is the last stop',
                    'next_action': 'end_trip',
                    'endpoint': f'/api/rentals/{rental_id}/end_trip/'
                }
        except Exception:
            return None

    @action(detail=True, methods=['get'], url_path='review_for_owner')
    def review_for_owner(self, request, pk=None):
        """
        يعرض كل تفاصيل الحجز للمالك قبل القبول أو الرفض
        """
        rental = self.get_object()
        user = request.user
        # تحقق أن المستخدم هو المالك
        if rental.car.owner != user:
            return Response({
                'error_code': 'NOT_OWNER',
                'error_message': 'فقط مالك السيارة يمكنه مراجعة تفاصيل الحجز.'
            }, status=403)
        # بيانات المستأجر
        renter = rental.renter
        renter_info = {
            'id': renter.id,
            'name': renter.get_full_name() or renter.email,
            'email': renter.email,
            'phone': renter.phone_number,
            'avg_rating': getattr(renter, 'avg_rating', None),
            'total_reviews': getattr(renter, 'total_reviews', None),
            'reports_count': getattr(renter, 'reports_count', None),
            'national_id': getattr(renter, 'national_id', None),
        }
        # بيانات السيارة
        car = rental.car
        car_info = {
            'id': car.id,
            'brand': car.brand,
            'model': car.model,
            'year': car.year,
            'category': getattr(car, 'category', None),
            'type': getattr(car, 'car_type', None),
            'plate_number': getattr(car, 'plate_number', None),
        }
        # بيانات التكلفة
        breakdown = getattr(rental, 'breakdown', None)
        cost_info = {
            'deposit': float(breakdown.deposit) if breakdown else None,
            'final_cost': float(breakdown.final_cost) if breakdown else None,
            'base_cost': float(breakdown.base_cost) if breakdown else None,
            'platform_fee': float(breakdown.platform_fee) if breakdown and hasattr(breakdown, 'platform_fee') else None,
            'driver_earnings': float(breakdown.driver_earnings) if breakdown and hasattr(breakdown, 'driver_earnings') else None,
            'allowed_km': float(breakdown.allowed_km) if breakdown else None,
            'planned_km': float(breakdown.planned_km) if breakdown else None,
            'total_waiting_minutes': int(breakdown.total_waiting_minutes) if breakdown else None,
        }
        # بيانات العربون
        from .models import RentalPayment
        try:
            payment = RentalPayment.objects.get(rental=rental)  # type: ignore
            deposit_status = payment.deposit_paid_status
            deposit_due_at = payment.deposit_due_at
        except RentalPayment.DoesNotExist:
            deposit_status = None
            deposit_due_at = None
        # بيانات المحطات
        from .models import PlannedTripStop
        stops = PlannedTripStop.objects.filter(planned_trip__rental_id=rental.id).order_by('stop_order')
        stops_info = [
            {
                'stop_order': stop.stop_order,
                'address': stop.address,
                'latitude': float(stop.latitude),
                'longitude': float(stop.longitude),
                'approx_waiting_time_minutes': stop.approx_waiting_time_minutes
            }
            for stop in stops
        ]
        # الرد النهائي - النقاط الأساسية فقط
        return Response({
            'rental_id': rental.id,
            'status': rental.status,
            'start_date': rental.start_date,
            'end_date': rental.end_date,
            'pickup_address': rental.pickup_address,
            'dropoff_address': rental.dropoff_address,
            'payment_method': rental.payment_method,
            'renter_name': renter.get_full_name() or renter.email,
            'renter_phone': renter.phone_number,
            'renter_rating': getattr(renter, 'avg_rating', 0),
            'car_info': f"{car.brand} {car.model} {car.year}",
            'total_cost': float(breakdown.final_cost) if breakdown else 0,
            'deposit_amount': float(breakdown.deposit) if breakdown else 0,
            'driver_earnings': float(breakdown.driver_earnings) if breakdown and hasattr(breakdown, 'driver_earnings') else 0,
            'stops_count': len(stops_info),
            'trip_stops': [
                {
                    'stop_order': stop.stop_order,
                    'address': stop.address,
                    'waiting_minutes': stop.approx_waiting_time_minutes
                }
                for stop in stops
            ],
            'can_confirm': rental.status == 'PendingOwnerConfirmation',
            'can_reject': rental.status == 'PendingOwnerConfirmation'
        })

    @staticmethod
    def create_rental_breakdown(rental, planned_km, total_waiting_minutes):
        car = rental.car
        options = car.rental_options
        policy = car.usage_policy
        start_date = rental.start_date
        end_date = rental.end_date
        payment_method = rental.payment_method
        daily_price = options.daily_rental_price_with_driver or 0
        daily_km_limit = float(policy.daily_km_limit)
        extra_km_rate = float(policy.extra_km_cost or 0)
        extra_hour_cost = float(policy.extra_hour_cost or 0)
        breakdown_data = calculate_rental_financials(
            start_date,
            end_date,
            float(planned_km),
            int(total_waiting_minutes),
            payment_method,
            float(daily_price),
            daily_km_limit,
            extra_km_rate,
            extra_hour_cost
        )
        breakdown, _ = RentalBreakdown.objects.update_or_create(  # type: ignore
            rental=rental,
            defaults={
                'planned_km': planned_km,
                'total_waiting_minutes': total_waiting_minutes,
                'daily_price': daily_price,
                'extra_km_cost': breakdown_data['extra_km_cost'],
                'waiting_cost': breakdown_data['waiting_cost'],
                'total_cost': breakdown_data['total_cost'],
                'deposit': breakdown_data['deposit'],
                'platform_fee': breakdown_data['platform_fee'],
                'driver_earnings': breakdown_data['driver_earnings'],
                'allowed_km': breakdown_data['allowed_km'],
                'extra_km': breakdown_data['extra_km'],
                'base_cost': breakdown_data['base_cost'],
                'final_cost': breakdown_data['final_cost'],
                'commission_rate': 0.1,
            }
        )
        payment, _ = RentalPayment.objects.get_or_create(rental=rental)  # type: ignore
        payment.deposit_amount = breakdown_data['deposit']
        payment.payment_method = payment_method
        payment.remaining_amount = breakdown_data['remaining']
        payment.limits_excess_insurance_amount = breakdown_data['limits_excess_insurance_amount']
        payment.platform_fee = breakdown_data['platform_fee'] if hasattr(payment, 'platform_fee') else None
        payment.driver_earnings = breakdown_data['driver_earnings'] if hasattr(payment, 'driver_earnings') else None
        payment.save()

    @staticmethod
    def dummy_charge_visa_or_wallet(user, amount, method):
        """
        دفع الزيادات باستخدام payment gateway مع الكارت المحفوظ
        """
        try:
            from payments.models import SavedCard
            from payments.services.payment_gateway import pay_with_saved_card_gateway
            
            # البحث عن الكارت المحفوظ للمستخدم
            saved_card = SavedCard.objects.filter(user=user).first()  # type: ignore
            if not saved_card:
                return {
                    'success': False,
                    'message': 'لا يوجد كارت محفوظ للمستخدم',
                    'error_code': 'NO_SAVED_CARD'
                }
            
            # تحويل المبلغ إلى قروش
            amount_cents = int(round(float(amount) * 100))
            
            # استخدام payment gateway
            result = pay_with_saved_card_gateway(amount_cents, user, saved_card.token)
            
            return result
                
        except Exception as e:
            return {
                'success': False,
                'message': f'خطأ في عملية الدفع: {str(e)}',
                'error_code': 'PAYMENT_ERROR'
            }

    @action(detail=True, methods=['get'], url_path='summary')
    def summary(self, request, pk=None):
        """
        ملخص شامل للحجز يتضمن جميع التفاصيل والمدفوعات وعمليات المحفظة
        """
        rental = self.get_object()
        
        # ===== VALIDATIONS =====
        
        # التحقق من الصلاحيات - المالك أو المستأجر فقط
        if rental.car.owner != request.user and rental.renter != request.user:
            return Response({
                'error_code': 'NOT_AUTHORIZED',
                'error_message': 'فقط مالك السيارة أو المستأجر يمكنه عرض ملخص الحجز.'
            }, status=403)
        
        # ===== GATHERING DATA =====
        
        # بيانات الحجز الأساسية
        breakdown = getattr(rental, 'breakdown', None)
        from .models import RentalPayment, PlannedTripStop, RentalLog
        
        try:
            payment = RentalPayment.objects.get(rental=rental)
        except RentalPayment.DoesNotExist:
            payment = None
        
        # المحطات
        stops = PlannedTripStop.objects.filter(planned_trip__rental_id=rental.id).order_by('stop_order')
        
        # سجل الأحداث
        logs = RentalLog.objects.filter(rental=rental).order_by('-timestamp')
        
        # ===== CALCULATIONS =====
        
        # حساب المبالغ
        total_amount = float(breakdown.final_total_cost or breakdown.final_cost or 0) if breakdown else 0
        deposit_amount = float(breakdown.deposit or 0) if breakdown else 0
        remaining_amount = float(payment.remaining_amount or 0) if payment else 0
        excess_amount = float(payment.excess_amount or 0) if payment else 0
        
        # إعادة حساب الأرباح والعمولة على السعر النهائي
        commission_rate = 0.1  # 10% عمولة المنصة
        platform_fee = total_amount * commission_rate
        driver_earnings = total_amount - platform_fee
        
        # ===== RESPONSE =====
        
        return Response({
            'rental_summary': {
                'rental_id': rental.id,
                'status': rental.status,
                'created_at': rental.created_at.isoformat() if hasattr(rental, 'created_at') else None,
                'updated_at': rental.updated_at.isoformat() if hasattr(rental, 'updated_at') else None,
                'trip_dates': {
                    'start_date': rental.start_date,
                    'end_date': rental.end_date,
                    'duration_days': (rental.end_date - rental.start_date).days + 1
                },
                'locations': {
                    'pickup_address': rental.pickup_address,
                    'dropoff_address': rental.dropoff_address
                },
                'payment_method': rental.payment_method,
                'selected_card': {
                    'brand': rental.selected_card.card_brand if rental.selected_card else None,
                    'last_four': rental.selected_card.card_last_four_digits if rental.selected_card else None
                } if rental.selected_card else None
            },
            'participants': {
                'driver': {
                    'id': rental.car.owner.id,
                    'name': rental.car.owner.get_full_name() or rental.car.owner.email,
                    'phone': rental.car.owner.phone_number,
                    'email': rental.car.owner.email,
                    'rating': getattr(rental.car.owner, 'avg_rating', 0),
                    'total_trips': getattr(rental.car.owner, 'completed_trips', 0)
                },
                'renter': {
                    'id': rental.renter.id,
                    'name': rental.renter.get_full_name() or rental.renter.email,
                    'phone': rental.renter.phone_number,
                    'email': rental.renter.email,
                    'rating': getattr(rental.renter, 'avg_rating', 0),
                    'total_trips': getattr(rental.renter, 'completed_trips', 0)
                }
            },
            'car_details': {
                'id': rental.car.id,
                'brand': rental.car.brand,
                'model': rental.car.model,
                'year': rental.car.year,
                'plate_number': rental.car.plate_number,
                'color': rental.car.color,
                'category': getattr(rental.car, 'category', None),
                'car_type': getattr(rental.car, 'car_type', None)
            },
            'financial_summary': {
                'total_amount': total_amount,
                'deposit_amount': deposit_amount,
                'remaining_amount': remaining_amount,
                'excess_amount': excess_amount,
                'driver_earnings': driver_earnings,
                'platform_fee': platform_fee,
                'commission_rate': f"{commission_rate * 100}%",
                'breakdown': {
                    'base_cost': float(breakdown.base_cost or 0) if breakdown else 0,
                    'extra_km_cost': float(breakdown.extra_km_cost or 0) if breakdown else 0,
                    'waiting_cost': float(breakdown.waiting_cost or 0) if breakdown else 0,
                    'excess_waiting_cost': float(breakdown.excess_waiting_cost or 0) if breakdown else 0,
                    'planned_km': float(breakdown.planned_km or 0) if breakdown else 0,
                    'allowed_km': float(breakdown.allowed_km or 0) if breakdown else 0,
                    'total_waiting_minutes': int(breakdown.total_waiting_minutes or 0) if breakdown else 0,
                    'actual_total_waiting_minutes': int(breakdown.actual_total_waiting_minutes or 0) if breakdown else 0,
                    'extra_waiting_minutes': int(breakdown.extra_waiting_minutes or 0) if breakdown else 0
                }
            },
            'payment_status': {
                'deposit_paid': payment.deposit_paid_status == 'Paid' if payment else False,
                'deposit_paid_at': payment.deposit_paid_at.isoformat() if payment and payment.deposit_paid_at else None,
                'deposit_transaction_id': payment.deposit_transaction_id if payment else None,
                'remaining_paid': payment.remaining_paid_status == 'Paid' if payment else False,
                'remaining_paid_at': payment.remaining_paid_at.isoformat() if payment and payment.remaining_paid_at else None,
                'remaining_transaction_id': payment.remaining_transaction_id if payment else None,
                'excess_paid': getattr(payment, 'excess_paid_status', None) == 'Paid' if payment else False,
                'excess_paid_at': getattr(payment, 'excess_paid_at', None).isoformat() if payment and getattr(payment, 'excess_paid_at', None) else None,
                'excess_transaction_id': getattr(payment, 'excess_transaction_id', None) if payment else None,
                'payout_processed': getattr(payment, 'payout_processed', False) if payment else False,
                'payout_processed_at': getattr(payment, 'payout_processed_at', None).isoformat() if payment and getattr(payment, 'payout_processed_at', None) else None
            },
            'trip_progress': {
                'owner_arrival_confirmed': rental.owner_arrival_confirmed,
                'owner_arrived_at_pickup': rental.owner_arrived_at_pickup.isoformat() if rental.owner_arrived_at_pickup else None,
                'renter_on_way_announced': rental.renter_on_way_announced,
                'renter_on_way_announced_at': rental.renter_on_way_announced_at.isoformat() if rental.renter_on_way_announced_at else None,
                'trip_started': rental.status in ['Ongoing', 'Finished', 'Completed'],
                'trip_finished': rental.status in ['Finished', 'Completed']
            },
            'stops_summary': {
                'total_stops': stops.count(),
                'stops_details': [
                    {
                        'stop_order': stop.stop_order,
                        'address': stop.address,
                        'latitude': float(stop.latitude),
                        'longitude': float(stop.longitude),
                        'planned_waiting_minutes': stop.approx_waiting_time_minutes,
                        'actual_waiting_minutes': stop.actual_waiting_minutes,
                        'arrived_at': stop.waiting_started_at.isoformat() if stop.waiting_started_at else None,
                        'left_at': stop.waiting_ended_at.isoformat() if stop.waiting_ended_at else None,
                        'location_verified': stop.location_verified
                    }
                    for stop in stops
                ]
            },
            'wallet_operations': {
                'driver_earnings_transferred': getattr(payment, 'driver_earnings_transferred', False) if payment else False,
                'platform_fee_deducted': getattr(payment, 'platform_fee_deducted', False) if payment else False,
                'operations_count': len(getattr(payment, 'wallet_operations', [])) if payment else 0
            },
            'activity_log': {
                'total_events': logs.count(),
                'recent_events': [
                    {
                        'event': log.event,
                        'performed_by_type': log.performed_by_type,
                        'performed_by': log.performed_by.get_full_name() if log.performed_by else 'System',
                        'timestamp': log.timestamp.isoformat()
                    }
                    for log in logs[:10]  # آخر 10 أحداث فقط
                ]
            },
            'permissions': {
                'can_view': True,
                'can_edit': rental.car.owner == request.user and rental.status in ['PendingOwnerConfirmation'],
                'can_cancel': rental.car.owner == request.user and rental.status in ['PendingOwnerConfirmation'],
                'can_start_trip': rental.car.owner == request.user and rental.status == 'Confirmed',
                'can_end_trip': rental.car.owner == request.user and rental.status == 'Ongoing',
                'can_process_payout': rental.car.owner == request.user and rental.status == 'Finished'
            },
            'next_actions': {
                'owner': [
                    'Confirm booking' if rental.status == 'PendingOwnerConfirmation' else None,
                    'Confirm arrival' if rental.status == 'Confirmed' and not rental.owner_arrival_confirmed else None,
                    'Start trip' if rental.status == 'Confirmed' and rental.owner_arrival_confirmed else None,
                    'End trip' if rental.status == 'Ongoing' else None,
                    'Process payout' if rental.status == 'Finished' else None
                ],
                'renter': [
                    'Pay deposit' if rental.status == 'DepositRequired' else None,
                    'Announce on way' if rental.status == 'Confirmed' and rental.owner_arrival_confirmed else None
                ]
            }
        })

    @action(detail=True, methods=['post'], url_path='cancel_rental')
    def cancel_rental(self, request, pk=None):
        """
        إلغاء الحجز من المالك مع رد العربون إن وجد
        """
        rental = self.get_object()
        
        # ===== VALIDATIONS =====
        
        # 1. التحقق من الصلاحيات - المالك فقط
        if rental.car.owner != request.user:
            return Response({
                'error_code': 'NOT_OWNER',
                'error_message': 'فقط مالك السيارة يمكنه إلغاء الحجز.'
            }, status=403)
        
        # 2. التحقق من حالة الحجز
        if rental.status == 'Canceled':
            return Response({
                'error_code': 'ALREADY_CANCELED',
                'error_message': 'تم إلغاء الحجز بالفعل.'
            }, status=400)
        
        # 3. لا يمكن الإلغاء إذا بدأت الرحلة
        if rental.status in ['Ongoing', 'Finished', 'Completed']:
            return Response({
                'error_code': 'TRIP_ALREADY_STARTED',
                'error_message': 'لا يمكن إلغاء الحجز بعد بدء الرحلة.'
            }, status=400)
        
        # 4. لا يمكن الإلغاء إذا تم تأكيد وصول المالك
        if rental.owner_arrival_confirmed:
            return Response({
                'error_code': 'OWNER_ARRIVED',
                'error_message': 'لا يمكن إلغاء الحجز بعد تأكيد وصول المالك.'
            }, status=400)
        
        # ===== PROCESSING =====
        
        try:
            payment = RentalPayment.objects.get(rental=rental)
        except RentalPayment.DoesNotExist:
            payment = None
        
        # معالجة رد العربون إذا كان مدفوع
        deposit_refund_details = None
        if payment and payment.deposit_paid_status == 'Paid':
            try:
                from wallets.models import Wallet, WalletTransaction, TransactionType
                from wallets.services import WalletService
                from decimal import Decimal
                
                renter = rental.renter
                wallet_service = WalletService()
                
                deposit_amount = Decimal(str(payment.deposit_amount))
                
                # إضافة المبلغ للمحفظة
                wallet_transaction = wallet_service.add_funds_to_wallet(
                    user=renter,
                    amount=deposit_amount,
                    transaction_type_name='Deposit Refund',
                    description=f'استرداد العربون لإلغاء رحلة #{rental.id} من المالك',
                    reference_id=str(rental.id),
                    reference_type='rental'
                )
                
                # تحديث حالة الدفع
                payment.deposit_paid_status = 'Refunded'
                payment.deposit_refunded_status = 'Refunded'
                payment.deposit_refunded_at = timezone.now()
                payment.deposit_refund_transaction_id = f'REFUND-{rental.id}-{int(payment.deposit_refunded_at.timestamp())}'
                payment.save()
                
                # تفاصيل الرد
                deposit_refund_details = {
                    'deposit_amount': float(payment.deposit_amount),
                    'deposit_refunded': True,
                    'deposit_refunded_at': payment.deposit_refunded_at.isoformat(),
                    'deposit_refund_transaction_id': payment.deposit_refund_transaction_id,
                    'wallet_transaction_id': wallet_transaction.id if wallet_transaction else None,
                    'refund_status': 'تم الرد بنجاح',
                    'refund_note': 'تم رد العربون إلى محفظة المستأجر'
                }
                
            except Exception as e:
                # في حالة فشل الرد، نستمر في الإلغاء ولكن نضع ملاحظة
                deposit_refund_details = {
                    'deposit_amount': float(payment.deposit_amount),
                    'deposit_refunded': False,
                    'refund_status': 'فشل في الرد',
                    'refund_note': f'فشل في رد العربون: {str(e)}'
                }
        
        elif payment and payment.deposit_paid_status != 'Paid':
            deposit_refund_details = {
                'deposit_amount': float(payment.deposit_amount) if payment.deposit_amount else 0,
                'deposit_refunded': False,
                'refund_status': 'لا يوجد ما يُرد',
                'refund_note': 'لم يتم دفع العربون أصلاً، لذلك لا يوجد ما يُرد.'
            }
        
        # ===== UPDATE RENTAL STATUS =====
        
        old_status = rental.status
        rental.status = 'Canceled'
        rental.save()
        
        # ===== LOG THE EVENT =====
        
        RentalLog.objects.create(
            rental=rental,
            event='Rental canceled by owner',
            performed_by_type='Owner',
            performed_by=request.user,
            details=f'Rental canceled from {old_status} to Canceled'
        )
        
        # ===== SEND NOTIFICATION =====
        
        try:
            from notifications.models import Notification
            Notification.objects.create(
                receiver=rental.renter,
                title="تم إلغاء الحجز",
                message=f"تم إلغاء حجزك لسيارة {rental.car.brand} {rental.car.model} من قبل المالك",
                notification_type="RENTAL_CANCELED",
                data={
                    'rental_id': rental.id,
                    'canceled_by': 'owner',
                    'deposit_refunded': deposit_refund_details.get('deposit_refunded', False) if deposit_refund_details else False
                }
            )
        except Exception as e:
            # تجاهل أخطاء الإشعارات
            pass
        
        # ===== RESPONSE =====
        
        return Response({
            'status': 'success',
            'message': 'تم إلغاء الحجز بنجاح.',
            'details': {
                'rental_id': rental.id,
                'old_status': old_status,
                'new_status': 'Canceled',
                'canceled_by': 'owner',
                'canceled_at': timezone.now().isoformat()
            },
            'deposit_refund': deposit_refund_details,
            'next_actions': [
                'Rental is now canceled',
                'Deposit refunded to renter wallet (if applicable)',
                'Both parties can create new rentals'
            ]
        })

class NewCardDepositPaymentView(APIView):
    """
    دفع العربون بكارت جديد للـ regular rentals (نفس نظام self-drive)
    POST /api/rentals/{{rental_id}}/new_card_deposit_payment/
    """
    permission_classes = [IsAuthenticated]

    def post(self, request, rental_id):
        """
        يبدأ عملية دفع الديبوزيت بكارت جديد (يرجع رابط iframe فقط)
        """
        user = request.user
        amount_cents = request.data.get('amount_cents')
        payment_method = request.data.get('payment_method')
        payment_type = request.data.get('type', 'deposit')
        rental = get_object_or_404(Rental, id=rental_id)
        if rental.status != 'DepositRequired':
            return Response({'error_code': 'OWNER_CONFIRMATION_REQUIRED', 'error_message': 'يجب أن يؤكد مالك السيارة الحجز أولاً قبل دفع العربون.'}, status=400)
        if rental.renter != user:
            return Response({'error_code': 'NOT_RENTER', 'error_message': 'يجب أن تكون المستأجر في هذا الحجز.'}, status=403)
        try:
            payment = RentalPayment.objects.get(rental=rental)  # type: ignore
        except RentalPayment.DoesNotExist:  # type: ignore
            return Response({'error_code': 'PAYMENT_NOT_FOUND', 'error_message': 'لا يوجد بيانات دفع مرتبطة بهذا الحجز.'}, status=400)
        if not payment or not hasattr(rental, 'breakdown'):
            return Response({'error_code': 'PAYMENT_NOT_FOUND', 'error_message': 'لا يوجد بيانات دفع مرتبطة بهذا الحجز.'}, status=400)
        if not hasattr(payment, 'deposit_amount') or not payment.deposit_amount:
            payment.deposit_amount = rental.breakdown.deposit
            payment.save()
        required_cents = int(round(float(payment.deposit_amount) * 100))
        if not amount_cents or int(amount_cents) != required_cents:
            return Response({'error_code': 'INVALID_AMOUNT', 'error_message': f'المبلغ المطلوب للعربون هو {required_cents} قرش.'}, status=400)
        if payment.deposit_paid_status == 'Paid':
            return Response({'error_code': 'ALREADY_PAID', 'error_message': 'تم دفع العربون بالفعل.'}, status=400)
        if payment_method != 'new_card':
            return Response({'error_code': 'INVALID_METHOD', 'error_message': 'طريقة الدفع يجب أن تكون new_card.'}, status=400)
        try:
            from payments.services import paymob
            from django.conf import settings
            auth_token = paymob.get_auth_token()
            import uuid
            reference = str(uuid.uuid4())
            user_id = str(user.id)
            merchant_order_id_with_user = f"{reference}_{user_id}"
            order_id = paymob.create_order(auth_token, amount_cents, merchant_order_id_with_user)
            integration_id = settings.PAYMOB_INTEGRATION_ID_CARD
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
            payment_token = paymob.get_payment_token(
                auth_token, order_id, amount_cents, billing_data, integration_id
            )
            iframe_url = f"https://accept.paymob.com/api/acceptance/iframes/{settings.PAYMOB_IFRAME_ID}?payment_token={payment_token}"
            payment.deposit_transaction_id = order_id
            payment.save()
            return Response({
                'iframe_url': iframe_url,
                'order_id': order_id,
                'message': 'يرجى إكمال الدفع عبر الرابط'
            })
        except Exception as e:
            return Response({'error_code': 'PAYMOB_ERROR', 'error_message': str(e)}, status=500)

    def get(self, request, rental_id):
        user = request.user
        rental = get_object_or_404(Rental, id=rental_id)
        if rental.renter != user:
            return Response({'error_code': 'NOT_RENTER', 'error_message': 'يجب أن تكون المستأجر في هذا الحجز.'}, status=403)
        try:
            payment = RentalPayment.objects.get(rental=rental)  # type: ignore
        except RentalPayment.DoesNotExist:  # type: ignore
            return Response({'error_code': 'PAYMENT_NOT_FOUND', 'error_message': 'لا يوجد بيانات دفع مرتبطة بهذا الحجز.'}, status=400)
        from .serializers import RentalPaymentSerializer
        return Response({
            'deposit_paid_status': payment.deposit_paid_status,
            'deposit_paid_at': payment.deposit_paid_at,
            'deposit_transaction_id': payment.deposit_transaction_id,
            'payment': RentalPaymentSerializer(payment).data,
        })