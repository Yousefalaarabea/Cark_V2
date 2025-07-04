from rest_framework import serializers
from .models import Rental, RentalPayment, PlannedTrip, PlannedTripStop, RentalBreakdown
from cars.models import Car, CarRentalOptions, CarUsagePolicy
from users.models import User
from payments.models import SavedCard
from rest_framework.decorators import action
from rest_framework.response import Response
from .services import dummy_charge_visa  # type: ignore

# Serializer لعرض بيانات المستخدم
class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ['id', 'email', 'phone_number', 'first_name', 'last_name', 'national_id']

# Serializer للكارت المحفوظ
class SavedCardSerializer(serializers.ModelSerializer):
    class Meta:
        model = SavedCard
        fields = ['id', 'card_brand', 'card_last_four_digits', 'created_at']

# Serializer لخيارات الإيجار للسيارة
class CarRentalOptionsSerializer(serializers.ModelSerializer):
    class Meta:
        model = CarRentalOptions
        fields = ['available_with_driver', 'available_without_driver', 'daily_rental_price', 'daily_rental_price_with_driver']

# Serializer لسياسة استخدام السيارة
class CarUsagePolicySerializer(serializers.ModelSerializer):
    class Meta:
        model = CarUsagePolicy
        fields = ['daily_km_limit', 'extra_km_cost', 'daily_hour_limit', 'extra_hour_cost']

# Serializer لعرض بيانات السيارة مع الخيارات والسياسة
class CarSerializer(serializers.ModelSerializer):
    rental_options = CarRentalOptionsSerializer(read_only=True)
    usage_policy = CarUsagePolicySerializer(read_only=True)
    class Meta:
        model = Car
        fields = ['id', 'brand', 'model', 'car_type', 'car_category', 'plate_number', 'year', 'color', 'seating_capacity', 'transmission_type', 'fuel_type', 'rental_options', 'usage_policy']

# Serializer لمحطة الرحلة
class PlannedTripStopSerializer(serializers.ModelSerializer):
    class Meta:
        model = PlannedTripStop
        fields = ['id', 'stop_order', 'latitude', 'longitude', 'approx_waiting_time_minutes', 'address', 'actual_waiting_minutes', 'waiting_started_at', 'waiting_ended_at', 'location_verified', 'is_completed']

# Serializer للرحلة المخططة مع المحطات
class PlannedTripSerializer(serializers.ModelSerializer):
    stops = PlannedTripStopSerializer(many=True)
    class Meta:
        model = PlannedTrip
        fields = ['id', 'route_polyline', 'stops']

# Serializer لبيانات الدفع
class RentalPaymentSerializer(serializers.ModelSerializer):
    class Meta:
        model = RentalPayment
        fields = [
            'deposit_amount', 'deposit_paid_status', 'deposit_paid_at', 'deposit_transaction_id',
            'deposit_refunded_status', 'deposit_refunded_at', 'deposit_refund_transaction_id',
            'remaining_amount', 'remaining_paid_status', 'remaining_paid_at', 'remaining_transaction_id',
            'limits_excess_insurance_amount', 'limits_refunded_status', 'limits_refunded_at', 'limits_refund_transaction_id',
            'payment_method', 'rental_total_amount'
        ]

# Serializer لتفاصيل breakdown
class RentalBreakdownSerializer(serializers.ModelSerializer):
    class Meta:
        model = RentalBreakdown
        fields = [
            'planned_km', 'total_waiting_minutes', 'daily_price', 'extra_km_cost', 'waiting_cost',
            'total_cost', 'deposit', 'platform_fee', 'driver_earnings',
            'allowed_km', 'extra_km', 'base_cost', 'final_cost', 'commission_rate',
            'created_at', 'updated_at'
        ]

# Serializer رئيسي لعرض الحجز بكل التفاصيل
class RentalSerializer(serializers.ModelSerializer):
    renter = UserSerializer(read_only=True)
    car = CarSerializer(read_only=True)
    planned_trip = PlannedTripSerializer(read_only=True)
    payment_info = RentalPaymentSerializer(read_only=True)
    breakdown = RentalBreakdownSerializer(read_only=True)
    selected_card = SavedCardSerializer(read_only=True)
    class Meta:
        model = Rental
        fields = [
            'id', 'renter', 'car', 'start_date', 'end_date', 'status',
            'rental_type',
            'pickup_lat', 'pickup_lng', 'dropoff_lat', 'dropoff_lng', 'pickup_address', 'dropoff_address',
            'payment_method', 'selected_card', 'created_at', 'updated_at', 'planned_trip', 'payment_info', 'breakdown',
            'owner_arrival_confirmed', 'owner_arrived_at_pickup', 'renter_on_way_announced', 'renter_on_way_announced_at'
        ]

# Serializer لإنشاء/تحديث الحجز مع المحطات
class RentalCreateUpdateSerializer(serializers.ModelSerializer):
    stops = PlannedTripStopSerializer(many=True, write_only=True)
    selected_card_id = serializers.IntegerField(write_only=True, required=False, help_text="ID of the saved card to use for payments (Required for visa payment method)")
    
    class Meta:
        model = Rental
        fields = [
            'car', 'start_date', 'end_date', 'rental_type',
            'pickup_lat', 'pickup_lng', 'dropoff_lat', 'dropoff_lng', 'pickup_address', 'dropoff_address',
            'payment_method', 'selected_card_id', 'stops'
        ]

    def validate(self, data):
        # تحقق من وجود السيارة والتواريخ والمحطات
        if not data.get('car'):
            raise serializers.ValidationError('Car is required.')
        if not data.get('start_date') or not data.get('end_date'):
            raise serializers.ValidationError('Start and end dates are required.')
        if not data.get('stops') or len(data.get('stops')) == 0:
            raise serializers.ValidationError('At least one stop is required.')
        
        # تحقق من selected_card_id validation
        selected_card_id = data.get('selected_card_id')
        payment_method = data.get('payment_method')
        
        # للـ visa payment: selected_card_id مطلوب إجبارياً
        if payment_method == 'visa':
            if not selected_card_id:
                raise serializers.ValidationError({
                    'selected_card_id': 'selected_card_id is required for visa payment method.'
                })
        
        # للـ cash payment: selected_card_id ممنوع
        elif payment_method == 'cash':
            if selected_card_id:
                raise serializers.ValidationError({
                    'selected_card_id': 'selected_card_id is not allowed for cash payment method. Deposit payments are handled separately.'
                })
        
        # تحقق من وجود الكارت إذا تم إدخاله (للـ visa فقط)
        if selected_card_id:
            try:
                card = SavedCard.objects.get(id=selected_card_id)  # type: ignore
                # ملاحظة: user ownership سيتم التحقق منه في create method
            except SavedCard.DoesNotExist:  # type: ignore
                raise serializers.ValidationError({
                    'selected_card_id': f'SavedCard with id {selected_card_id} does not exist.'
                })
        
        return data

    def create(self, validated_data):
        stops_data = validated_data.pop('stops')
        selected_card_id = validated_data.pop('selected_card_id', None)
        
        # Create rental
        rental = Rental.objects.create(**validated_data)  # type: ignore
        
        # Set selected card if provided and validate ownership
        if selected_card_id:
            try:
                card = SavedCard.objects.get(id=selected_card_id, user=self.context['request'].user)  # type: ignore
                rental.selected_card = card
                rental.save()
            except SavedCard.DoesNotExist:  # type: ignore
                raise serializers.ValidationError(f'SavedCard with id {selected_card_id} does not exist or does not belong to you.')
        
        # Create planned trip and stops
        planned_trip = PlannedTrip.objects.create(rental=rental)  # type: ignore
        for stop in stops_data:
            PlannedTripStop.objects.create(planned_trip=planned_trip, **stop)  # type: ignore
        return rental

    def update(self, instance, validated_data):
        stops_data = validated_data.pop('stops', None)
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()
        if stops_data is not None:
            planned_trip = instance.planned_trip
            planned_trip.stops.all().delete()
            for stop in stops_data:
                PlannedTripStop.objects.create(planned_trip=planned_trip, **stop)  # type: ignore
        return instance

@action(detail=True, methods=['post'])
def confirm_booking(self, request, pk=None):
    rental = self.get_object()
    if rental.status != 'Pending':
        return Response({'error': 'Cannot confirm booking unless status is Pending.'}, status=400)
    contract_type = request.data.get('contract_type')
    if contract_type:
        rental.contract_type = contract_type
    rental.status = 'Confirmed'
    rental.save()

    # --- هنا منطق الدفع الوهمي ---
    # جلب قيمة العربون من breakdown
    if hasattr(rental, 'breakdown'):
        deposit_amount = rental.breakdown.deposit
        # نفذ الدفع فقط لو طريقة الدفع visa
        if rental.payment_method == 'visa':
            success = dummy_charge_visa(rental.renter, deposit_amount)
            if success:
                # حدث حالة الدفع في RentalPayment أو سجل العملية
                payment, _ = RentalPayment.objects.get_or_create(rental=rental)  # type: ignore
                payment.deposit_amount = deposit_amount
                payment.deposit_paid_status = 'Paid'
                payment.save()
    # --- نهاية منطق الدفع ---

    return Response({'status': 'Booking confirmed.', 'contract_type': rental.contract_type})
