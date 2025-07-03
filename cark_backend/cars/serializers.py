from rest_framework import serializers
from .models import Car, CarRentalOptions, CarUsagePolicy, CarStats

class CarSerializer(serializers.ModelSerializer):
    class Meta:
        model = Car
        fields = '__all__'
        read_only_fields = ['owner']  # 👈 هنا نخليه read-only

    def validate_year(self, value):
        import datetime
        current_year = datetime.datetime.now().year
        if value < 1900 or value > current_year + 1:
            raise serializers.ValidationError("Year must be between 1900 and next year.")
        return value

    def validate_seating_capacity(self, value):
        if value <= 0:
            raise serializers.ValidationError("Seating capacity must be greater than 0.")
        return value

    def validate_current_odometer_reading(self, value):
        if value < 0:
            raise serializers.ValidationError("Odometer reading cannot be negative.")
        if self.instance and value < self.instance.current_odometer_reading:
            raise serializers.ValidationError("Odometer reading cannot decrease from the previous value.")
        return value

    def validate_plate_number(self, value):
        if not value.strip():
            raise serializers.ValidationError("Plate number cannot be empty.")
        # OPTIONAL regex check
        import re
        pattern = r'^[A-Z]{3}\d{3}$'
        if not re.match(pattern, value):
            raise serializers.ValidationError("Plate number must match format: 3 letters + 3 digits (e.g., ABC123).")
        return value


class CarRentalOptionsSerializer(serializers.ModelSerializer):
    class Meta:
        model = CarRentalOptions
        fields = '__all__'

    def validate(self, data):
        prices = [
            data.get('daily_rental_price'),
            data.get('monthly_rental_price'),
            data.get('yearly_rental_price'),
            data.get('daily_rental_price_with_driver'),
            data.get('monthly_price_with_driver'),
            data.get('yearly_price_with_driver'),
        ]

        if all(price in [None, 0] for price in prices):
            raise serializers.ValidationError("At least one rental price must be set.")

        return data


class CarUsagePolicySerializer(serializers.ModelSerializer):
    class Meta:
        model = CarUsagePolicy
        fields = '__all__'

    def validate_daily_km_limit(self, value):
        if value <= 0:
            raise serializers.ValidationError("Daily KM limit must be greater than 0.")
        return value

    def validate_extra_km_cost(self, value):
        if value < 0:
            raise serializers.ValidationError("Extra KM cost cannot be negative.")
        return value

    def validate_extra_hour_cost(self, value):
        if value is not None and value < 0:
            raise serializers.ValidationError("Extra hour cost cannot be negative.")
        return value

    def validate_daily_hour_limit(self, value):
        if value is not None and value <= 0:
            raise serializers.ValidationError("Daily hour limit must be greater than 0 if provided.")
        return value


class CarStatsSerializer(serializers.ModelSerializer):
    class Meta:
        model = CarStats
        fields = '__all__'

    def validate_rental_history_count(self, value):
        if value < 0:
            raise serializers.ValidationError("Rental history count cannot be negative.")
        return value

    def validate_total_earned(self, value):
        if value < 0:
            raise serializers.ValidationError("Total earned cannot be negative.")
        return value


# New detailed serializer for available cars with all related data
class DetailedCarSerializer(serializers.ModelSerializer):
    rental_options = CarRentalOptionsSerializer(read_only=True)
    usage_policy = CarUsagePolicySerializer(read_only=True)
    stats = CarStatsSerializer(read_only=True)
    images = serializers.SerializerMethodField()
    
    class Meta:
        model = Car
        fields = [
            'id', 'owner', 'model', 'brand', 'car_type', 'car_category',
            'plate_number', 'year', 'color', 'seating_capacity',
            'transmission_type', 'fuel_type', 'current_odometer_reading',
            'availability', 'current_status', 'created_at', 'updated_at',
            'approval_status', 'avg_rating', 'total_reviews',
            'rental_options', 'usage_policy', 'stats', 'images'
        ]
        read_only_fields = ['owner', 'created_at', 'updated_at']
    
    def get_images(self, obj):
        """
        جلب صور السيارة من الـ documents المربوطة بيها
        """
        from documents.models import Document
        
        # جلب كل الـ documents الخاصة بالسيارة
        car_documents = Document.objects.filter(car=obj)  # type: ignore
        
        images = []
        for doc in car_documents:
            if doc.file:
                # بناء الـ URL الكامل للصورة
                image_url = None
                if hasattr(self, 'context') and 'request' in self.context:
                    request = self.context['request']
                    image_url = request.build_absolute_uri(doc.file.url)
                else:
                    image_url = doc.file.url
                
                images.append({
                    'id': doc.id,
                    'url': image_url,
                    'document_type': doc.document_type.name if doc.document_type else None,
                    'status': doc.status,
                    'upload_date': doc.upload_date
                })
        
        return images
