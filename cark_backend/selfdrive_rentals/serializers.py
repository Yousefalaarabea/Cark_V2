from rest_framework import serializers
from .models import SelfDriveRental, SelfDriveOdometerImage, SelfDriveContract, SelfDriveLiveLocation, SelfDrivePayment, SelfDriveRentalBreakdown, SelfDriveRentalLog, SelfDriveRentalStatusHistory
from rentals.serializers import UserSerializer, CarSerializer
from cars.models import Car

class SelfDriveOdometerImageSerializer(serializers.ModelSerializer):
    class Meta:
        model = SelfDriveOdometerImage
        fields = ['id', 'image', 'value', 'type', 'uploaded_at']
        read_only_fields = ['id', 'uploaded_at']

class SelfDriveContractSerializer(serializers.ModelSerializer):
    class Meta:
        model = SelfDriveContract
        fields = [
            'id', 'renter_signed', 'renter_signed_at', 'owner_signed', 'owner_signed_at',
            'contract_pdf', 'owner_contract_image', 'created_at', 'updated_at'
        ]
        read_only_fields = fields

class SelfDriveLiveLocationSerializer(serializers.ModelSerializer):
    class Meta:
        model = SelfDriveLiveLocation
        fields = ['id', 'latitude', 'longitude', 'timestamp']
        read_only_fields = ['id', 'timestamp']

class SelfDrivePaymentSerializer(serializers.ModelSerializer):
    class Meta:
        model = SelfDrivePayment
        fields = [
            'id',
            'deposit_amount', 'deposit_paid_status', 'deposit_paid_at', 'deposit_transaction_id',
            'deposit_refunded', 'deposit_refunded_at', 'deposit_refund_transaction_id',
            'remaining_amount', 'remaining_paid_status', 'remaining_paid_at', 'remaining_transaction_id',
            'excess_amount', 'excess_paid_status', 'excess_paid_at', 'excess_transaction_id',
            'payment_method', 'rental_total_amount',
            'created_at', 'updated_at'
        ]
        read_only_fields = fields

class SelfDriveRentalBreakdownSerializer(serializers.ModelSerializer):
    class Meta:
        model = SelfDriveRentalBreakdown
        fields = [
            'id', 'actual_dropoff_time',
            'num_days', 'daily_price',
            'base_cost', 'ctw_fee', 'initial_cost',
            'allowed_km', 'extra_km', 'extra_km_cost', 'extra_km_fee',
            'late_days', 'late_fee',
            'total_extras_cost', 'final_cost',
            'commission_rate', 'platform_earnings', 'driver_earnings',
            'created_at', 'updated_at'
        ]
        read_only_fields = fields

class SelfDriveRentalLogSerializer(serializers.ModelSerializer):
    user = serializers.StringRelatedField()
    class Meta:
        model = SelfDriveRentalLog
        fields = ['id', 'action', 'user', 'timestamp', 'details']
        read_only_fields = fields

class SelfDriveRentalStatusHistorySerializer(serializers.ModelSerializer):
    changed_by = serializers.StringRelatedField()
    class Meta:
        model = SelfDriveRentalStatusHistory
        fields = ['id', 'old_status', 'new_status', 'changed_by', 'timestamp']
        read_only_fields = fields

class SelfDriveRentalSerializer(serializers.ModelSerializer):
    car = serializers.PrimaryKeyRelatedField(queryset=Car.objects.all(), write_only=True)
    car_details = CarSerializer(source='car', read_only=True)
    renter = UserSerializer(read_only=True)
    pickup_latitude = serializers.DecimalField(max_digits=9, decimal_places=6, required=False, write_only=True)
    pickup_longitude = serializers.DecimalField(max_digits=9, decimal_places=6, required=False, write_only=True)
    dropoff_latitude = serializers.DecimalField(max_digits=9, decimal_places=6, required=False, write_only=True)
    dropoff_longitude = serializers.DecimalField(max_digits=9, decimal_places=6, required=False, write_only=True)
    odometer_images = SelfDriveOdometerImageSerializer(many=True, read_only=True)
    contract = SelfDriveContractSerializer(read_only=True)
    live_locations = SelfDriveLiveLocationSerializer(many=True, read_only=True)
    payment_info = serializers.SerializerMethodField()
    breakdown = SelfDriveRentalBreakdownSerializer(read_only=True)
    pickup_lat = serializers.SerializerMethodField()
    pickup_lng = serializers.SerializerMethodField()
    dropoff_lat = serializers.SerializerMethodField()
    dropoff_lng = serializers.SerializerMethodField()
    payment_method = serializers.CharField(write_only=True, required=False)
    logs = SelfDriveRentalLogSerializer(many=True, read_only=True)
    status_history = SelfDriveRentalStatusHistorySerializer(many=True, read_only=True)
    selected_card = serializers.IntegerField(write_only=True, required=False)

    def validate_payment_method(self, value):
        allowed = ['cash', 'visa', 'wallet']
        if value.lower() not in allowed:
            raise serializers.ValidationError("نوع الدفع غير مدعوم. اختر cash أو visa أو wallet.")
        return value.lower()

    def get_payment_info(self, obj):
        if hasattr(obj, 'payment') and obj.payment:
            data = SelfDrivePaymentSerializer(obj.payment).data
            # camelCase keys for payment_method
            if 'payment_method' in data:
                data['payment_method'] = data['payment_method'].lower()
            return data
        return None

    def get_pickup_lat(self, obj):
        return str(obj.pickup_latitude) if obj.pickup_latitude is not None else None
    def get_pickup_lng(self, obj):
        return str(obj.pickup_longitude) if obj.pickup_longitude is not None else None
    def get_dropoff_lat(self, obj):
        return str(obj.dropoff_latitude) if obj.dropoff_latitude is not None else None
    def get_dropoff_lng(self, obj):
        return str(obj.dropoff_longitude) if obj.dropoff_longitude is not None else None

    def validate(self, attrs):
        payment_method = attrs.get('payment_method', 'cash').lower()
        selected_card = attrs.get('selected_card')
        user = self.context['request'].user if 'request' in self.context else None
        if payment_method == 'visa':
            if not selected_card:
                raise serializers.ValidationError({"selected_card": "يجب اختيار كارت فيزا عند اختيار طريقة الدفع فيزا."})
            from payments.models import SavedCard
            if user is None:
                raise serializers.ValidationError("لا يمكن التحقق من المستخدم.")
            try:
                card = SavedCard.objects.get(id=selected_card, user=user)
            except SavedCard.DoesNotExist:
                raise serializers.ValidationError({"selected_card": "الكارت غير موجود أو لا يخصك."})
        else:
            if selected_card:
                raise serializers.ValidationError({"selected_card": "لا يمكن إرسال selected_card إلا مع طريقة دفع فيزا فقط."})
        return attrs

    def create(self, validated_data):
        selected_card = validated_data.pop('selected_card', None)
        payment_method = validated_data.pop('payment_method', 'cash')
        instance = super().create(validated_data)
        instance._payment_method = payment_method.lower()
        if selected_card:
            instance.selected_card_id = selected_card
            instance.save(update_fields=["selected_card"])
        return instance

    class Meta:
        model = SelfDriveRental
        fields = [
            'id', 'renter', 'car', 'car_details', 'start_date', 'end_date',
            'status',
            'pickup_latitude', 'pickup_longitude', 'dropoff_latitude', 'dropoff_longitude',
            'pickup_lat', 'pickup_lng', 'dropoff_lat', 'dropoff_lng',
            'pickup_address', 'dropoff_address',
            'payment_method', 'created_at', 'updated_at',
            'odometer_images', 'contract', 'live_locations', 'payment_info', 'breakdown',
            'logs', 'status_history',
            'selected_card',
        ]
        read_only_fields = [
            'id', 'created_at', 'updated_at', 'odometer_images', 'contract', 'live_locations',
            'payment_info', 'breakdown', 'renter', 'car_details',
            'pickup_lat', 'pickup_lng', 'dropoff_lat', 'dropoff_lng', 'payment_method',
            'logs', 'status_history',
        ]
        extra_kwargs = {
            'car': {'write_only': True},
            'car_details': {'read_only': True},
            'pickup_latitude': {'write_only': True},
            'pickup_longitude': {'write_only': True},
            'dropoff_latitude': {'write_only': True},
            'dropoff_longitude': {'write_only': True},
        }
