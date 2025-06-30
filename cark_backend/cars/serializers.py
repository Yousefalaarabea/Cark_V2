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
