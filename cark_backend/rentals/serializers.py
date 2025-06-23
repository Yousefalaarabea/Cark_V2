from rest_framework import serializers
from .models import Rental, RentalPayment, RentalUsage, PlannedTrip, PlannedTripStop, RentalBreakdown
from cars.models import Car, CarRentalOptions, CarUsagePolicy
from users.models import User

# Serializer لعرض بيانات المستخدم
class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ['id', 'email', 'phone_number', 'first_name', 'last_name', 'national_id']

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

# Serializer لبيانات الاستخدام
class RentalUsageSerializer(serializers.ModelSerializer):
    class Meta:
        model = RentalUsage
        fields = ['start_odometer', 'end_odometer', 'total_distance_used', 'start_time', 'end_time', 'actual_return_time', 'extra_km', 'extra_km_charges', 'extra_hours', 'extra_hour_charges', 'total_waiting_minutes', 'extra_waiting_minutes', 'waiting_time_cost', 'pickup_confirmed_by_owner', 'pickup_confirmed_by_renter', 'dropoff_confirmed_by_owner', 'dropoff_confirmed_by_renter']

# Serializer لبيانات الدفع
class RentalPaymentSerializer(serializers.ModelSerializer):
    class Meta:
        model = RentalPayment
        fields = ['deposit_amount', 'deposit_paid_status', 'deposit_paid_at', 'insurance_amount', 'insurance_paid_status', 'insurance_paid_at', 'rental_paid_status', 'rental_paid_at', 'payment_method', 'refundable_buffer']

# Serializer لتفاصيل breakdown
class RentalBreakdownSerializer(serializers.ModelSerializer):
    class Meta:
        model = RentalBreakdown
        fields = [
            'planned_km', 'total_waiting_minutes', 'daily_price', 'extra_km_cost', 'waiting_cost',
            'total_cost', 'buffer_amount', 'deposit', 'platform_fee', 'driver_earnings',
            'allowed_km', 'extra_km', 'base_cost', 'final_cost', 'commission_rate',
            'created_at', 'updated_at'
        ]

# Serializer رئيسي لعرض الحجز بكل التفاصيل
class RentalSerializer(serializers.ModelSerializer):
    renter = UserSerializer(read_only=True)
    car = CarSerializer(read_only=True)
    planned_trip = PlannedTripSerializer(read_only=True)
    usage_info = RentalUsageSerializer(read_only=True)
    payment_info = RentalPaymentSerializer(read_only=True)
    breakdown = RentalBreakdownSerializer(read_only=True)
    class Meta:
        model = Rental
        fields = [
            'id', 'renter', 'car', 'start_date', 'end_date', 'status', 'negotiation_status',
            'rental_type', 'pickup_lat', 'pickup_lng', 'dropoff_lat', 'dropoff_lng', 'pickup_address', 'dropoff_address',
            'payment_method', 'insurance_buffer', 'deposit', 'platform_commission', 'driver_earnings', 'contract_type', 'contract_signed',
            'created_at', 'updated_at', 'planned_trip', 'usage_info', 'payment_info', 'breakdown'
        ]

# Serializer لإنشاء/تحديث الحجز مع المحطات
class RentalCreateUpdateSerializer(serializers.ModelSerializer):
    stops = PlannedTripStopSerializer(many=True, write_only=True)
    class Meta:
        model = Rental
        fields = [
            'car', 'start_date', 'end_date', 'rental_type',
            'pickup_lat', 'pickup_lng', 'dropoff_lat', 'dropoff_lng', 'pickup_address', 'dropoff_address',
            'payment_method', 'stops'
        ]

    def validate(self, data):
        # تحقق من وجود السيارة والتواريخ والمحطات
        if not data.get('car'):
            raise serializers.ValidationError('Car is required.')
        if not data.get('start_date') or not data.get('end_date'):
            raise serializers.ValidationError('Start and end dates are required.')
        if not data.get('stops') or len(data.get('stops')) == 0:
            raise serializers.ValidationError('At least one stop is required.')
        return data

    def create(self, validated_data):
        stops_data = validated_data.pop('stops')
        rental = Rental.objects.create(**validated_data)
        planned_trip = PlannedTrip.objects.create(rental=rental)
        for stop in stops_data:
            PlannedTripStop.objects.create(planned_trip=planned_trip, **stop)
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
                PlannedTripStop.objects.create(planned_trip=planned_trip, **stop)
        return instance
