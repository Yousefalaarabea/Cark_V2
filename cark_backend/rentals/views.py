from django.http import HttpResponse
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from .models import Rental, PlannedTrip, PlannedTripStop, RentalUsage, RentalPayment, RentalBreakdown
from .serializers import RentalSerializer, RentalCreateUpdateSerializer, PlannedTripStopSerializer, RentalBreakdownSerializer
from .services import calculate_rental_financials
from cars.models import Car
from django.shortcuts import get_object_or_404
from django.db import transaction

def home(request):
    return HttpResponse("Welcome to Rentals Home!")

class RentalViewSet(viewsets.ModelViewSet):
    """
    ViewSet رئيسي لإدارة جميع خطوات فلو الإيجار مع السائق:
    - إنشاء الحجز
    - حساب التكاليف
    - تأكيد الحجز
    - توقيع العقد
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
        breakdown = rental.breakdown
        return Response(RentalBreakdownSerializer(breakdown).data)

    @action(detail=True, methods=['post'])
    def confirm_booking(self, request, pk=None):
        """
        تأكيد الحجز من قبل المالك (مع تحديد نوع العقد)
        """
        rental = self.get_object()
        if rental.status != 'Pending':
            return Response({'error': 'Cannot confirm booking unless status is Pending.'}, status=400)
        contract_type = request.data.get('contract_type')
        if contract_type:
            rental.contract_type = contract_type  # owner يحدد نوع العقد هنا
        rental.status = 'Confirmed'
        rental.save()
        return Response({'status': 'Booking confirmed.', 'contract_type': rental.contract_type})

    @action(detail=True, methods=['post'])
    def sign_contract(self, request, pk=None):
        """
        توقيع العقد (ورقي أو إلكتروني)
        """
        rental = self.get_object()
        if rental.status != 'Confirmed':
            return Response({'error': 'Contract can only be signed after confirmation.'}, status=400)
        rental.contract_signed = True
        rental.status = 'contractSigned'
        rental.save()
        return Response({'status': 'Contract signed.'})

    @action(detail=True, methods=['post'])
    def start_trip(self, request, pk=None):
        """
        بدء الرحلة (يتطلب تحقق من الموقع في التطبيق الفعلي)
        """
        rental = self.get_object()
        if rental.status != 'contractSigned':
            return Response({'error': 'Trip can only be started after contract is signed.'}, status=400)
        rental.status = 'Ongoing'
        rental.save()
        return Response({'status': 'Trip started.'})

    @action(detail=True, methods=['post'])
    def stop_arrival(self, request, pk=None):
        """
        تأكيد وصول السائق للمحطة (مع تحقق الموقع)
        """
        stop_id = request.data.get('stop_id')
        if not stop_id:
            return Response({'error': 'stop_id is required.'}, status=400)
        stop = get_object_or_404(PlannedTripStop, id=stop_id, planned_trip__rental_id=pk)
        # تحقق من الموقع (GPS)
        stop.location_verified = True
        stop.waiting_started_at = request.data.get('waiting_started_at')
        stop.save()
        return Response({'status': 'Stop arrival confirmed.'})

    @action(detail=True, methods=['post'])
    def end_waiting(self, request, pk=None):
        """
        إنهاء الانتظار في محطة معينة وتسجيل الوقت الفعلي
        """
        stop_id = request.data.get('stop_id')
        if not stop_id:
            return Response({'error': 'stop_id is required.'}, status=400)
        actual_waiting_minutes = int(request.data.get('actual_waiting_minutes', 0))
        stop = get_object_or_404(PlannedTripStop, id=stop_id, planned_trip__rental_id=pk)
        stop.waiting_ended_at = request.data.get('waiting_ended_at')
        stop.actual_waiting_minutes = actual_waiting_minutes
        stop.save()
        return Response({'status': 'Waiting ended.'})

    @action(detail=True, methods=['post'])
    def end_trip(self, request, pk=None):
        """
        إنهاء الرحلة (يتطلب تحقق من الموقع في التطبيق الفعلي)
        """
        rental = self.get_object()
        if rental.status != 'Ongoing':
            return Response({'error': 'Trip can only be ended if it is ongoing.'}, status=400)
        rental.status = 'Finished'
        rental.save()
        # حساب الفاتورة النهائية (يمكنك استدعاء دوال الحسابات هنا)
        return Response({'status': 'Trip ended. Final billing will be processed.'})

    @action(detail=True, methods=['post'])
    def payout(self, request, pk=None):
        """
        توزيع الأرباح وخصم عمولة المنصة بعد نهاية الرحلة
        """
        rental = self.get_object()
        if rental.status != 'Finished':
            return Response({'error': 'Payout can only be processed after trip is finished.'}, status=400)
        # منطق توزيع الأرباح والعمولة (يمكنك التوسع فيه لاحقاً)
        return Response({'status': 'Payout processed.'})

# دالة مساعدة لإنشاء breakdown
def create_rental_breakdown(rental, planned_km, total_waiting_minutes):
    car = rental.car
    options = car.rental_options
    policy = car.usage_policy
    rental_days = (rental.end_date - rental.start_date).days + 1
    payment_method = rental.payment_method
    daily_price = options.daily_rental_price_with_driver or 0
    extra_km_rate = policy.extra_km_cost or 0
    waiting_hour_rate = policy.extra_hour_cost or 0
    commission_rate = 0.2
    breakdown_data = calculate_rental_financials(
        rental_days,
        planned_km,
        float(policy.daily_km_limit),
        float(extra_km_rate),
        total_waiting_minutes,
        float(waiting_hour_rate),
        float(daily_price),
        payment_method,
        commission_rate
    )
    # حفظ breakdown
    RentalBreakdown.objects.update_or_create(
        rental=rental,
        defaults={
            'planned_km': planned_km,
            'total_waiting_minutes': total_waiting_minutes,
            'daily_price': daily_price,
            'extra_km_cost': breakdown_data['extra_km_cost'],
            'waiting_cost': breakdown_data['waiting_time_cost'],
            'total_cost': breakdown_data['total_costs'],
            'buffer_amount': breakdown_data['insurance_buffer'],
            'deposit': breakdown_data['deposit'],
            'platform_fee': breakdown_data['platform_commission'],
            'driver_earnings': breakdown_data['driver_earnings'],
            'allowed_km': breakdown_data['allowed_km'],
            'extra_km': breakdown_data['extra_km'],
            'base_cost': breakdown_data['base_cost'],
            'final_cost': breakdown_data['final_cost'],
            'commission_rate': commission_rate,
        }
    )