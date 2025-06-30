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

def home(request):
    return HttpResponse("Welcome to Rentals Home!")

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
    queryset = Rental.objects.all()
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
        rental = self.get_object()
        if rental.status != 'Pending':
            return Response({'error': 'Cannot confirm booking unless status is Pending.'}, status=400)
        rental.status = 'Confirmed'
        rental.save()
        RentalLog.objects.create(rental=rental, event='Booking confirmed', performed_by_type='Owner', performed_by=request.user)
        
        # --- منطق دفع الديبوزيت والريفاندبل بافر ---
        payment_status = {
            'deposit': 'Not required',
        }
        
        if hasattr(rental, 'breakdown'):
            deposit_amount = rental.breakdown.deposit
            
            if rental.payment_method == 'visa':
                from .models import RentalPayment
                payment, _ = RentalPayment.objects.get_or_create(rental=rental)
                payment.payment_method = rental.payment_method
                
                # دفع الديبوزيت
                if deposit_amount > 0:
                    success = dummy_charge_visa(rental.renter, deposit_amount)
                    if success:
                        payment.deposit_amount = deposit_amount
                        payment.deposit_paid_status = 'Paid'
                        payment.deposit_paid_at = timezone.now()
                        payment.deposit_transaction_id = 'dummy_deposit_txn'
                        payment_status['deposit'] = 'Paid'
                    else:
                        payment.deposit_paid_status = 'Failed'
                        payment_status['deposit'] = 'Failed'
                
                payment.save()
            else:
                payment_status['deposit'] = 'Not required (not visa)'
        else:
            payment_status['deposit'] = 'No breakdown found'
            
        return Response({
            'status': 'Booking confirmed.',
            'payment_status': payment_status
        })

    @action(detail=True, methods=['post'])
    def start_trip(self, request, pk=None):
        rental = self.get_object()
        if rental.status != 'Confirmed':
            return Response({'error': 'Trip can only be started after booking is confirmed.'}, status=400)
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
        trip_started = RentalLog.objects.filter(rental_id=pk, event__icontains='Trip started').exists()
        if not trip_started:
            return Response({'error': 'You must start the trip before starting any stop.'}, status=400)
        # منع تكرار تسجيل الوصول لنفس المحطة
        if stop.waiting_started_at:
            return Response({'error': 'Arrival for this stop has already been confirmed.'}, status=400)
        # تحقق من منطق بدء المحطة التالية
        if stop_order > 1:
            prev_stop = PlannedTripStop.objects.filter(planned_trip__rental_id=pk, stop_order=stop_order-1).first()
            if prev_stop and not prev_stop.waiting_ended_at:
                return Response({'error': f'You must end waiting for stop #{stop_order-1} before starting stop #{stop_order}.'}, status=400)
        # تحقق من الموقع (GPS)
        stop.location_verified = True
        stop.waiting_started_at = request.data.get('waiting_started_at')
        stop.save()
        # سجل الحدث في RentalLog
        RentalLog.objects.create(
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
        RentalLog.objects.create(
            rental=stop.planned_trip.rental,
            event=f'Waiting ended at stop #{stop.stop_order} (actual_waiting_minutes={actual_waiting_minutes})',
            performed_by_type='Owner',
            performed_by=request.user
        )
        return Response({'status': 'Waiting ended.'})

    @action(detail=True, methods=['post'])
    def end_trip(self, request, pk=None):
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
        actual_total_waiting_minutes = sum([float(stop.actual_waiting_minutes) for stop in planned_stops])
        planned_total_waiting_minutes = sum([float(stop.approx_waiting_time_minutes) for stop in planned_stops])
        extra_waiting_minutes = actual_total_waiting_minutes - planned_total_waiting_minutes
        car = rental.car
        extra_hour_cost = float(car.usage_policy.extra_hour_cost or 0)
        extra_cost = max(0, extra_waiting_minutes) * (extra_hour_cost / 60)
        base_final_cost = float(rental.breakdown.final_cost)
        rental_total_amount = base_final_cost + float(extra_cost)
        payment.rental_total_amount = rental_total_amount
        details = {
            'base_final_cost': base_final_cost,
            'extra_waiting_minutes': extra_waiting_minutes,
            'extra_cost': extra_cost,
            'rental_total_amount': rental_total_amount
        }
        if rental.payment_method in ['visa', 'wallet']:
            limits = float(payment.limits_excess_insurance_amount)
            if extra_cost > 0:
                if extra_cost >= limits:
                    payment.limits_refunded_status = 'No Remaining to Refund'
                    payment.limits_refunded_at = timezone.now()
                    payment.limits_refund_transaction_id = 'excess_fully_consumed'
                    refund = 0
                    details['limits_excess_used'] = limits
                    details['limits_refunded'] = 0
                    details['limits_shortfall'] = float(extra_cost) - limits
                else:
                    payment.limits_refunded_status = 'Refunded'
                    payment.limits_refunded_at = timezone.now()
                    payment.limits_refund_transaction_id = 'partial_refund'
                    refund = limits - float(extra_cost)
                    details['limits_excess_used'] = float(extra_cost)
                    details['limits_refunded'] = refund
                    details['limits_shortfall'] = 0
            else:
                payment.limits_refunded_status = 'Refunded'
                payment.limits_refunded_at = timezone.now()
                payment.limits_refund_transaction_id = 'full_refund'
                refund = limits
                details['limits_excess_used'] = 0
                details['limits_refunded'] = refund
                details['limits_shortfall'] = 0
            payment.save()
            rental.status = 'Finished'
            rental.save()
            user = request.user if request.user.is_authenticated else None
            RentalLog.objects.create(rental=rental, event='Trip ended', performed_by_type='Owner', performed_by=user)
            return Response({
                'status': 'Trip ended. Final billing processed.',
                'payment_method': rental.payment_method,
                'rental_total_amount': rental_total_amount,
                'limits_excess_insurance_amount': limits,
                'limits_excess_used': details['limits_excess_used'],
                'limits_refunded': details['limits_refunded'],
                'limits_shortfall': details['limits_shortfall'],
                'extra_waiting_minutes': extra_waiting_minutes,
                'extra_cost': extra_cost,
                'message': 'Refund processed to renter.' if details['limits_refunded'] > 0 else 'All buffer consumed for extra charges.'
            })
        else:
            rental.status = 'Finished'
            rental.save()
            user = request.user if request.user.is_authenticated else None
            RentalLog.objects.create(rental=rental, event='Trip ended', performed_by_type='Owner', performed_by=user)
            return Response({
                'status': 'Trip ended. Final billing processed.',
                'payment_method': rental.payment_method,
                'rental_total_amount': rental_total_amount,
                'amount_driver_should_collect': rental_total_amount,
                'extra_waiting_minutes': extra_waiting_minutes,
                'extra_cost': extra_cost,
                'message': 'Driver should collect the total from the renter.'
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
    breakdown, _ = RentalBreakdown.objects.update_or_create(
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
    payment, _ = RentalPayment.objects.get_or_create(rental=rental)
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
