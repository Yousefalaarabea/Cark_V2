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
            create_rental_breakdown(rental, planned_km, total_waiting_minutes)
            from .models import RentalPayment
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
            
            # Send notification to car owner
            from notifications.models import Notification
            Notification.objects.create(
                user=rental.car.owner,
                title="New Rental Request",
                message=f"New rental request for your {rental.car.brand} {rental.car.model} from {rental.pickup_address}",
                notification_type="rental_request",
                data={'rental_id': rental.id}
            )
            
        return Response(RentalSerializer(rental).data, status=status.HTTP_201_CREATED)

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
        if rental.status != 'PendingOwnerConfirmation':
            return Response({
                'error_code': 'INVALID_STATUS', 
                'error_message': 'Cannot confirm booking unless status is PendingOwnerConfirmation.'
            }, status=400)
        
        # Check owner permission
        if rental.car.owner != request.user:
            return Response({
                'error_code': 'NOT_OWNER', 
                'error_message': 'Only car owner can confirm booking.'
            }, status=403)
        
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
            user=rental.renter,
            title="Rental Confirmed",
            message=f"Your rental for {rental.car.brand} {rental.car.model} has been confirmed. Please pay deposit within 24 hours.",
            notification_type="rental_confirmed",
            data={'rental_id': rental.id, 'deposit_amount': float(payment.deposit_amount or 0)}
        )
        
        return Response({
            'status': 'Booking confirmed by owner.',
            'message': 'Renter must pay deposit within 24 hours.',
            'old_status': old_status,
            'new_status': rental.status,
            'deposit_due_at': payment.deposit_due_at
                 })

    @action(detail=True, methods=['post'])
    def owner_confirm_arrival(self, request, pk=None):
        """
        تأكيد وصول المالك لموقع الاستلام (pickup location)
        """
        rental = self.get_object()
        
        # التحقق من الصلاحيات
        if rental.car.owner != request.user:
            return Response({
                'error_code': 'NOT_OWNER',
                'error_message': 'Only the car owner can confirm arrival.'
            }, status=403)
        
        # التحقق من الحالة
        if rental.status != 'Confirmed':
            return Response({
                'error_code': 'INVALID_STATUS',
                'error_message': f'Owner can only confirm arrival when rental is Confirmed. Current status: {rental.status}'
            }, status=400)
        
        # التحقق من عدم التكرار
        if rental.owner_arrival_confirmed:
            return Response({
                'error_code': 'ALREADY_CONFIRMED',
                'error_message': 'Owner arrival has already been confirmed.',
                'confirmed_at': rental.owner_arrived_at_pickup
            }, status=400)
        
        # تأكيد الوصول
        rental.owner_arrival_confirmed = True
        rental.owner_arrived_at_pickup = timezone.now()
        rental.save()
        
        # تسجيل الحدث
        RentalLog.objects.create(
            rental=rental,
            event='Owner confirmed arrival at pickup location',
            performed_by_type='Owner',
            performed_by=request.user
        )
        
        # Send notification to renter
        from notifications.models import Notification
        Notification.objects.create(
            user=rental.renter,
            title="Driver Arrived",
            message=f"Your driver has arrived at {rental.pickup_address}. Trip will start soon.",
            notification_type="driver_arrived",
            data={'rental_id': rental.id, 'pickup_address': rental.pickup_address}
        )
        
        return Response({
            'status': 'Owner arrival confirmed.',
            'message': 'Owner has confirmed arrival at pickup location. Trip can now be started.',
            'confirmed_at': rental.owner_arrived_at_pickup,
            'pickup_address': rental.pickup_address
        })

    @action(detail=True, methods=['post'])
    def deposit_payment(self, request, pk=None):
        """
        دفع العربون بكارت محفوظ (نفس نظام self-drive)
        صفحة منفصلة بطرق دفع منفصلة
        """
        rental = self.get_object()
        
        # ===== BASIC VALIDATIONS (same as self-drive) =====
        
        # 1. Check if owner confirmed first
        if rental.status != 'DepositRequired':
            return Response({
                'error_code': 'OWNER_CONFIRMATION_REQUIRED',
                'error_message': f'يجب أن يؤكد مالك السيارة الحجز أولاً قبل دفع العربون. الحالة الحالية: {rental.status}'
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
                    user=rental.car.owner,
                    title="Deposit Paid",
                    message=f"Deposit paid for rental of {rental.car.brand} {rental.car.model}. Ready for pickup confirmation.",
                    notification_type="deposit_paid",
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
        
        # 1. Check if owner confirmed first
        if rental.status != 'DepositRequired':
            return Response({
                'error_code': 'OWNER_CONFIRMATION_REQUIRED',
                'error_message': f'Rental status must be DepositRequired, current status: {rental.status}'
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
            payment = RentalPayment.objects.get(rental=rental)
            if payment.deposit_paid_status == 'Paid':
                return Response({
                    'error_code': 'ALREADY_PAID',
                    'error_message': 'Deposit has already been paid.',
                    'transaction_id': payment.deposit_transaction_id,
                    'paid_at': payment.deposit_paid_at
                }, status=400)
        except RentalPayment.DoesNotExist:
            payment = RentalPayment.objects.create(rental=rental)
        
        # 4. Check breakdown exists and deposit amount
        if not hasattr(rental, 'breakdown'):
            return Response({
                'error_code': 'BREAKDOWN_NOT_FOUND',
                'error_message': 'Rental breakdown not found. Please calculate costs first.'
            }, status=400)
        
        deposit_amount = rental.breakdown.deposit
        if not deposit_amount or float(deposit_amount) <= 0:
            return Response({
                'error_code': 'NO_DEPOSIT_REQUIRED',
                'error_message': 'No deposit is required for this rental.',
                'deposit_amount': deposit_amount
            }, status=400)
        
        # 5. Check deposit due date
        if hasattr(payment, 'deposit_due_at') and payment.deposit_due_at:
            if timezone.now() > payment.deposit_due_at:
                return Response({
                    'error_code': 'DEPOSIT_EXPIRED',
                    'error_message': 'Deposit payment deadline has expired.',
                    'due_date': payment.deposit_due_at
                }, status=400)
        
        # 6. Check rental payment method - all payment methods now support deposit
        # Even cash rentals require electronic deposit payment
        
        # Special validation for wallet rentals (not implemented for new cards)
        if rental.payment_method == 'wallet':
            return Response({
                'error_code': 'WALLET_PAYMENT_NOT_IMPLEMENTED',
                'error_message': 'Wallet deposit payments with new cards are not yet implemented.',
                'rental_payment_method': rental.payment_method,
                'suggestion': 'Please use visa payment method or saved card deposit.'
            }, status=501)
        
        # ===== REQUEST VALIDATION =====
        
        # 7. Get and validate amount_cents
        amount_cents = request.data.get('amount_cents')
        if not amount_cents:
            return Response({
                'error_code': 'MISSING_AMOUNT',
                'error_message': 'amount_cents is required.'
            }, status=400)
        
        # 7. Validate amount_cents format
        try:
            amount_cents = int(amount_cents)
            if amount_cents <= 0:
                raise ValueError("Amount must be positive")
        except (ValueError, TypeError):
            return Response({
                'error_code': 'INVALID_AMOUNT_FORMAT',
                'error_message': 'amount_cents must be a positive integer.'
            }, status=400)
        
        # 8. Check amount matches required deposit  
        required_cents = int(round(float(deposit_amount) * 100))
        if amount_cents != required_cents:
            return Response({
                'error_code': 'INVALID_AMOUNT',
                'error_message': f'Amount mismatch. Required: {required_cents} cents, Provided: {amount_cents} cents.',
                'required_amount_cents': required_cents,
                'required_amount_egp': float(deposit_amount),
                'provided_amount_cents': amount_cents,
                'provided_amount_egp': amount_cents / 100
            }, status=400)
        
        # ===== PAYMENT INTENT CREATION =====
        try:
            
            # Create payment intent for new card
            from payments.services.paymob import create_payment_intent_for_deposit
            intent_response = create_payment_intent_for_deposit(
                amount_cents=int(amount_cents),
                user=request.user,
                rental_id=rental.id
            )
            
            if not intent_response.get('success'):
                return Response({
                    'error_code': 'PAYMENT_INTENT_FAILED',
                    'error_message': intent_response.get('message', 'Failed to create payment intent.')
                }, status=400)
            
            # Return iframe URL for payment
            return Response({
                'status': 'Payment intent created successfully.',
                'iframe_url': intent_response['iframe_url'],
                'rental_id': rental.id,
                'amount_cents': amount_cents,
                'required_amount_cents': required_cents,
                'message': 'Complete payment using the provided iframe URL.'
            })
            
        except Exception as e:
            return Response({
                'error_code': 'PAYMENT_ERROR',
                'error_message': str(e)
            }, status=500)

    @action(detail=True, methods=['post'])
    def start_trip(self, request, pk=None):
        rental = self.get_object()
        
        # التحقق من الصلاحيات
        if rental.car.owner != request.user:
            return Response({
                'error_code': 'NOT_OWNER',
                'error_message': 'Only the car owner can start the trip.'
            }, status=403)
        
        # التحقق من الحالة
        if rental.status != 'Confirmed':
            return Response({
                'error_code': 'INVALID_STATUS',
                'error_message': 'Trip can only be started after deposit is paid and booking is confirmed.',
                'current_status': rental.status
            }, status=400)
        
        # التحقق من تأكيد وصول المالك
        if not rental.owner_arrival_confirmed:
            return Response({
                'error_code': 'OWNER_ARRIVAL_REQUIRED',
                'error_message': 'Owner must confirm arrival at pickup location before starting the trip.',
                'required_action': 'owner_confirm_arrival'
            }, status=400)
        from .models import RentalPayment
        payment, _ = RentalPayment.objects.get_or_create(rental=rental)
        payment.payment_method = rental.payment_method
        payment_status = None
        payment_message = None
        if rental.payment_method in ['visa', 'wallet']:
            amount_to_charge = payment.remaining_amount
            success = dummy_charge_visa_or_wallet(rental.renter, amount_to_charge, rental.payment_method)
            if not success:
                payment.remaining_paid_status = 'Failed'
                payment.save()
                return Response({
                    'status': 'Trip not started.',
                    'payment_method': rental.payment_method,
                    'payment_status': 'Failed',
                    'message': 'Payment for the remaining amount failed. Trip cannot be started.'
                }, status=402)
            payment.remaining_paid_status = 'Paid'
            payment.remaining_paid_at = timezone.now()
            payment.remaining_transaction_id = 'dummy_rental_txn'
            payment.save()
            payment_status = 'Paid'
            payment_message = 'Payment for the remaining amount succeeded. Trip started.'
        else:
            payment.remaining_paid_status = 'Pending'
            payment.save()
            payment_status = 'Pending'
            payment_message = 'Trip started. Remaining amount will be paid in cash.'
        rental.status = 'Ongoing'
        rental.save()
        user = request.user if request.user.is_authenticated else None
        RentalLog.objects.create(rental=rental, event='Trip started', performed_by_type='Owner', performed_by=user)
        
        # Send notification to renter
        from notifications.models import Notification
        Notification.objects.create(
            user=rental.renter,
            title="Trip Started",
            message=f"Your trip with {rental.car.brand} {rental.car.model} has started. Enjoy your ride!",
            notification_type="trip_started",
            data={'rental_id': rental.id, 'payment_method': rental.payment_method}
        )
        
        return Response({
            'status': 'Trip started.',
            'payment_method': rental.payment_method,
            'payment_status': payment_status,
            'message': payment_message
        })

    @action(detail=True, methods=['post'])
    def stop_arrival(self, request, pk=None):
        """
        تأكيد وصول السائق للمحطة (مع تحقق الموقع)
        """
        stop_order = request.data.get('stop_order')
        if stop_order is None:
            return Response({'error': 'stop_order is required.'}, status=400)
        stop_order = int(stop_order)
        stop = get_object_or_404(PlannedTripStop, stop_order=stop_order, planned_trip__rental_id=pk)
        # تحقق أولاً أن الرحلة بدأت
        from .models import RentalLog
        trip_started = RentalLog.objects.filter(rental_id=pk, event__icontains='Trip started').exists()  # type: ignore
        if not trip_started:
            return Response({'error': 'You must start the trip before starting any stop.'}, status=400)
        # منع تكرار تسجيل الوصول لنفس المحطة
        if stop.waiting_started_at:
            return Response({'error': 'Arrival for this stop has already been confirmed.'}, status=400)
        # تحقق من منطق بدء المحطة التالية
        if stop_order > 1:
            prev_stop = PlannedTripStop.objects.filter(planned_trip__rental_id=pk, stop_order=stop_order-1).first()  # type: ignore
            if prev_stop and not prev_stop.waiting_ended_at:
                return Response({'error': f'You must end waiting for stop #{stop_order-1} before starting stop #{stop_order}.'}, status=400)
        # تحقق من الموقع (GPS)
        stop.location_verified = True
        stop.waiting_started_at = request.data.get('waiting_started_at')
        stop.save()
        # سجل الحدث في RentalLog
        RentalLog.objects.create(  # type: ignore
            rental=stop.planned_trip.rental,
            event=f'Stop arrival confirmed (Stop #{stop.stop_order})',
            performed_by_type='Owner',
            performed_by=request.user
        )
        return Response({'status': 'Stop arrival confirmed.'})

    @action(detail=True, methods=['post'])
    def end_waiting(self, request, pk=None):
        """
        إنهاء الانتظار في محطة معينة وتسجيل الوقت الفعلي
        """
        stop_order = request.data.get('stop_order')
        if stop_order is None:
            return Response({'error': 'stop_order is required.'}, status=400)
        actual_waiting_minutes = int(request.data.get('actual_waiting_minutes', 0))
        stop = get_object_or_404(PlannedTripStop, stop_order=stop_order, planned_trip__rental_id=pk)
        # تحقق أنه تم بدء الانتظار فعلاً
        if not stop.waiting_started_at:
            return Response({'error': 'You must start waiting at this stop before you can end it.'}, status=400)
        # منع تكرار إنهاء الانتظار لنفس المحطة
        if stop.waiting_ended_at:
            return Response({'error': 'Waiting for this stop has already been ended.'}, status=400)
        stop.waiting_ended_at = request.data.get('waiting_ended_at')
        stop.actual_waiting_minutes = actual_waiting_minutes
        stop.save()
        # سجل الحدث في RentalLog
        RentalLog.objects.create(  # type: ignore
            rental=stop.planned_trip.rental,
            event=f'Waiting ended at stop #{stop.stop_order} (actual_waiting_minutes={actual_waiting_minutes})',
            performed_by_type='Owner',
            performed_by=request.user
        )
        return Response({'status': 'Waiting ended.'})

    @action(detail=True, methods=['post'])
    def end_trip(self, request, pk=None):
        """
        إنهاء الرحلة وحساب الزيادات (زي self-drive)
        """
        rental = self.get_object()
        if rental.status != 'Ongoing':
            return Response({'error': 'Trip can only be ended if it is ongoing.'}, status=400)
            
        from .models import RentalPayment, PlannedTripStop
        payment, _ = RentalPayment.objects.get_or_create(rental=rental)
        planned_stops = PlannedTripStop.objects.filter(planned_trip__rental_id=rental.id)
        
        # تحقق من إنهاء الانتظار في آخر محطة
        if planned_stops.exists():
            last_stop = planned_stops.order_by('-stop_order').first()
            if not last_stop.waiting_ended_at:
                return Response({'error': 'You must end waiting at the last stop before ending the trip.'}, status=400)
        
        # حساب الزيادات (زي self-drive)
        actual_total_waiting_minutes = int(sum([float(stop.actual_waiting_minutes) for stop in planned_stops]))
        planned_total_waiting_minutes = int(sum([float(stop.approx_waiting_time_minutes) for stop in planned_stops]))
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
        
        # منطق الدفع حسب نوع الرحلة (زي self-drive)
        if rental.payment_method in ['visa', 'wallet']:
            # للرحلات الإلكترونية: الزيادات تتدفع إلكترونياً
            if excess_amount > 0:
                # محتاج يدفع الزيادة إلكترونياً (simulate payment)
                success = dummy_charge_visa_or_wallet(request.user, excess_amount, rental.payment_method)
                if success:
                    message = f'Excess amount {excess_amount} EGP charged electronically.'
                else:
                    return Response({'error': 'Failed to charge excess amount electronically.'}, status=400)
            else:
                message = 'No excess charges.'
                
        else:
            # للرحلات الكاش: Owner يحصل الـ remaining + excess كاش
            remaining_amount = float(payment.remaining_amount or 0)
            cash_to_collect = remaining_amount + excess_amount
            message = f'Owner should collect {cash_to_collect} EGP cash (remaining: {remaining_amount}, excess: {excess_amount}).'
        
        # إنهاء الرحلة
            rental.status = 'Finished'
            rental.save()
        
        # تسجيل العملية
            user = request.user if request.user.is_authenticated else None
        RentalLog.objects.create(
            rental=rental, 
            event='Trip ended', 
            performed_by_type='Owner', 
            performed_by=user
        )
        
        return Response({
        'status': 'Trip ended successfully.',
            'payment_method': rental.payment_method,
        'base_cost': base_final_cost,
        'excess_amount': excess_amount,
        'final_amount': final_amount,
            'extra_waiting_minutes': extra_waiting_minutes,
        'remaining_amount': float(payment.remaining_amount or 0),
        'cash_to_collect': remaining_amount + excess_amount if rental.payment_method == 'cash' else 0,
        'message': message
        })

    @action(detail=True, methods=['post'])
    def payout(self, request, pk=None):
        rental = self.get_object()
        if rental.status != 'Finished':
            return Response({'error': 'Payout can only be processed after trip is finished.'}, status=400)
        RentalLog.objects.create(rental=rental, event='Payout processed', performed_by_type='Owner', performed_by=request.user)
        return Response({'status': 'Payout processed.'})

# دالة مساعدة لإنشاء breakdown
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
    from .models import RentalPayment
    payment, _ = RentalPayment.objects.get_or_create(rental=rental)  # type: ignore
    payment.deposit_amount = breakdown_data['deposit']
    payment.payment_method = payment_method
    payment.remaining_amount = breakdown_data['remaining']
    payment.limits_excess_insurance_amount = breakdown_data['limits_excess_insurance_amount']
    payment.platform_fee = breakdown_data['platform_fee'] if hasattr(payment, 'platform_fee') else None
    payment.driver_earnings = breakdown_data['driver_earnings'] if hasattr(payment, 'driver_earnings') else None
    payment.save()

def dummy_charge_visa_or_wallet(user, amount, method):
    print(f'[DUMMY] Charging {amount} from {user.username} using {method}...')
    return True  # دائماً ناجح (أو أرجع False للتجربة)

class NewCardDepositPaymentView(APIView):
    """
    دفع العربون بكارت جديد للـ regular rentals (نفس نظام self-drive)
    POST /api/rentals/{{rental_id}}/new_card_deposit_payment/
    """
    # permission_classes = [IsAuthenticated]  # مُعطل مؤقتاً للاختبار

    def post(self, request, rental_id):
        """
        يبدأ عملية دفع الديبوزيت بكارت جديد (يرجع رابط iframe فقط)
        """
        user = request.user
        amount_cents = request.data.get('amount_cents')
        payment_method = request.data.get('payment_method')
        payment_type = request.data.get('type', 'deposit')
        
        # تحقق من كل الفحوصات المطلوبة
        from .models import Rental
        rental = get_object_or_404(Rental, id=rental_id)
        
        # تأكد أن المالك أكد الحجز أولاً
        if rental.status != 'DepositRequired':
            return Response({
                'error_code': 'OWNER_CONFIRMATION_REQUIRED', 
                'error_message': 'يجب أن يؤكد مالك السيارة الحجز أولاً قبل دفع العربون.'
            }, status=400)
        
        if rental.renter != user:
            return Response({
                'error_code': 'NOT_RENTER', 
                'error_message': 'يجب أن تكون المستأجر في هذا الحجز.'
            }, status=403)
            
        # Get or create payment record
        from .models import RentalPayment
        try:
            payment = RentalPayment.objects.get(rental=rental)  # type: ignore
        except RentalPayment.DoesNotExist:  # type: ignore
            payment = RentalPayment.objects.create(rental=rental)  # type: ignore
        
        if not payment or not hasattr(rental, 'breakdown'):
            return Response({
                'error_code': 'PAYMENT_NOT_FOUND', 
                'error_message': 'لا يوجد بيانات دفع مرتبطة بهذا الحجز.'
            }, status=400)
            
        # Set deposit amount if not set
        if not hasattr(payment, 'deposit_amount') or not payment.deposit_amount:
            payment.deposit_amount = rental.breakdown.deposit
            payment.save()
            
        required_cents = int(round(float(payment.deposit_amount) * 100))
        if not amount_cents or int(amount_cents) != required_cents:
            return Response({
                'error_code': 'INVALID_AMOUNT', 
                'error_message': f'المبلغ المطلوب للعربون هو {required_cents} قرش.'
            }, status=400)
            
        if payment.deposit_paid_status == 'Paid':
            return Response({
                'error_code': 'ALREADY_PAID', 
                'error_message': 'تم دفع العربون بالفعل.'
            }, status=400)
            
        if payment_method != 'new_card':
            return Response({
                'error_code': 'INVALID_METHOD', 
                'error_message': 'طريقة الدفع يجب أن تكون new_card.'
            }, status=400)
            
        # تنفيذ منطق Paymob للبطاقات الجديدة (نفس self-drive)
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
            
            # حفظ order_id في payment لتتبع العملية
            payment.deposit_transaction_id = order_id  # مؤقتًا لتتبع العملية
            payment.save()
            
            return Response({
                'iframe_url': iframe_url,
                'order_id': order_id,
                'message': 'يرجى إكمال الدفع عبر الرابط'
            })
            
        except Exception as e:
            return Response({
                'error_code': 'PAYMOB_ERROR', 
                'error_message': str(e)
            }, status=500)

    def get(self, request, rental_id):
        """
        يرجع حالة الدفع وتفاصيل آخر عملية
        """
        user = request.user
        from .models import Rental
        rental = get_object_or_404(Rental, id=rental_id)
        
        if rental.renter != user:
            return Response({
                'error_code': 'NOT_RENTER', 
                'error_message': 'يجب أن تكون المستأجر في هذا الحجز.'
            }, status=403)
            
        from .models import RentalPayment
        try:
            payment = RentalPayment.objects.get(rental=rental)  # type: ignore
        except RentalPayment.DoesNotExist:  # type: ignore
            return Response({
                'error_code': 'PAYMENT_NOT_FOUND', 
                'error_message': 'لا يوجد بيانات دفع مرتبطة بهذا الحجز.'
            }, status=400)
            
        from .serializers import RentalPaymentSerializer
        return Response({
            'deposit_paid_status': payment.deposit_paid_status,
            'deposit_paid_at': payment.deposit_paid_at,
            'deposit_transaction_id': payment.deposit_transaction_id,
            'payment': RentalPaymentSerializer(payment).data,
        })
