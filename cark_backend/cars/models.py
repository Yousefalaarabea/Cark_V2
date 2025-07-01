from django.db import models
from django.contrib.auth import get_user_model

User = get_user_model()

class Car(models.Model):
    SUV = 'SUV'
    SEDAN = 'Sedan'
    HATCHBACK = 'Hatchback'
    TRUCK = 'Truck'
    VAN = 'Van'
    COUPE = 'Coupe'
    CONVERTIBLE = 'Convertible'
    OTHER = 'Other'

    ECONOMY = 'Economy'
    LUXURY = 'Luxury'
    SPORTS = 'Sports'
    OFFROAD = 'Off-road'
    ELECTRIC = 'Electric'

    MANUAL = 'Manual'
    AUTOMATIC = 'Automatic'

    PETROL = 'Petrol'
    DIESEL = 'Diesel'
    ELECTRIC_FUEL = 'Electric'
    HYBRID = 'Hybrid'

    AVAILABLE = 'Available'
    BOOKED = 'Booked'
    IN_USE = 'InUse'
    UNDER_MAINTENANCE = 'UnderMaintenance'

    CAR_TYPE_CHOICES = [
        (SUV, 'SUV'),
        (SEDAN, 'Sedan'),
        (HATCHBACK, 'Hatchback'),
        (TRUCK, 'Truck'),
        (VAN, 'Van'),
        (COUPE, 'Coupe'),
        (CONVERTIBLE, 'Convertible'),
        (OTHER, 'Other'),
    ]

    CAR_CATEGORY_CHOICES = [
        (ECONOMY, 'Economy'),
        (LUXURY, 'Luxury'),
        (SPORTS, 'Sports'),
        (OFFROAD, 'Off-road'),
        (ELECTRIC, 'Electric'),
        (OTHER, 'Other'),
    ]

    TRANSMISSION_CHOICES = [
        (MANUAL, 'Manual'),
        (AUTOMATIC, 'Automatic'),
    ]

    FUEL_CHOICES = [
        (PETROL, 'Petrol'),
        (DIESEL, 'Diesel'),
        (ELECTRIC_FUEL, 'Electric'),
        (HYBRID, 'Hybrid'),
        (OTHER, 'Other'),
    ]

    STATUS_CHOICES = [
        (AVAILABLE, 'Available'),
        (BOOKED, 'Booked'),
        (IN_USE, 'InUse'),
        (UNDER_MAINTENANCE, 'UnderMaintenance'),
    ]

    owner = models.ForeignKey(User, on_delete=models.CASCADE, related_name='cars')
    model = models.CharField(max_length=100)
    brand = models.CharField(max_length=100)
    car_type = models.CharField(max_length=20, choices=CAR_TYPE_CHOICES)
    car_category = models.CharField(max_length=20, choices=CAR_CATEGORY_CHOICES)
    plate_number = models.CharField(max_length=20, unique=True)
    year = models.IntegerField()
    color = models.CharField(max_length=50)
    seating_capacity = models.IntegerField()
    transmission_type = models.CharField(max_length=10, choices=TRANSMISSION_CHOICES)
    fuel_type = models.CharField(max_length=10, choices=FUEL_CHOICES)
    current_odometer_reading = models.IntegerField()
    availability = models.BooleanField(default=True)
    current_status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=AVAILABLE)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    approval_status = models.BooleanField(default=False)
    avg_rating = models.FloatField(default=0)
    total_reviews = models.PositiveIntegerField(default=0)

class CarRentalOptions(models.Model):
    car = models.OneToOneField(Car, on_delete=models.CASCADE, related_name='rental_options')
    available_without_driver = models.BooleanField(default=False)
    available_with_driver = models.BooleanField(default=False)

    daily_rental_price = models.DecimalField(max_digits=10, decimal_places=2 , null=True, blank=True)
    monthly_rental_price = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    yearly_rental_price = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)

    daily_rental_price_with_driver = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    monthly_price_with_driver = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    yearly_price_with_driver = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)

class CarUsagePolicy(models.Model):
    car = models.OneToOneField(Car, on_delete=models.CASCADE, related_name='usage_policy')
    daily_km_limit = models.DecimalField(max_digits=5, decimal_places=2)
    extra_km_cost = models.DecimalField(max_digits=5, decimal_places=2)
    daily_hour_limit = models.IntegerField(null=True, blank=True)
    extra_hour_cost = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)

class CarStats(models.Model):
    car = models.OneToOneField(Car, on_delete=models.CASCADE, related_name='stats')
    rental_history_count = models.IntegerField(default=0)
    total_earned = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    
