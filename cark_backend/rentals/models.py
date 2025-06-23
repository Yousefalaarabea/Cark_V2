from django.db import models
from django.contrib.auth import get_user_model
from cars.models import Car

User = get_user_model()

class Rental(models.Model):
    STATUS_CHOICES = [
        ('Pending', 'Pending'),
        ('Canceled', 'Canceled'),
        ('Confirmed', 'Confirmed'),
        ('Awaiting Deposit', 'Awaiting Deposit'),
        ('Deposit Paid', 'Deposit Paid'),
        ('Awaiting Contract', 'Awaiting Contract'),
        ('contractSigned', 'Contract Signed'),
        ('Awaiting Final Payment', 'Awaiting Final Payment'),
        ('Final Payment Paid', 'Final Payment Paid'),
        ('Ongoing', 'Ongoing'),
        ('Finished', 'Finished'),
    ]

    NEGOTIATION_STATUS_CHOICES = [
        ('NotNegotiated', 'Not Negotiated'),
        ('Pending', 'Pending'),
        ('Accepted', 'Accepted'),
        ('Rejected', 'Rejected'),
        ('Canceled', 'Canceled'),
        ('OwnerRejected', 'Owner Rejected'),
        ('RenterRejected', 'Renter Rejected'),
        ('OwnerAccepted', 'Owner Accepted'),
        ('RenterAccepted', 'Renter Accepted'),
    ]

    

    PROPOSED_BY_CHOICES = [('Owner', 'Owner'), ('Renter', 'Renter')]
    renter = models.ForeignKey(User, on_delete=models.CASCADE, related_name='rentals')
    car = models.ForeignKey(Car, on_delete=models.CASCADE, related_name='rentals')
     
    start_date = models.DateField()
    end_date = models.DateField()

    status = models.CharField(max_length=30, choices=STATUS_CHOICES, default='Pending')
    negotiation_status = models.CharField(max_length=30, choices=NEGOTIATION_STATUS_CHOICES, default='NotNegotiated')
    #نوع الايجار بدون سايقة أو مع سائق
    rental_type = models.CharField(max_length=20, choices=[('WithDriver', 'With Driver'), ('WithoutDriver', 'Without Driver')], default='WithDriver')
    # زون الايجار
    rental_zone_WithoutDriver = models.CharField(max_length=100, null=True, blank=True)
    
    # مواقع التقاط السيارة والتوصيل

    pickup_lat = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    pickup_lng = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    dropoff_lat = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    dropoff_lng = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    pickup_address = models.CharField(max_length=255, null=True, blank=True)
    dropoff_address = models.CharField(max_length=255, null=True, blank=True)

    # --- NEW FIELDS FOR WITH DRIVER FLOW ---
    PAYMENT_METHOD_CHOICES = [
        ('wallet', 'Wallet'),
        ('visa', 'Visa/Mastercard'),
        ('cash', 'Cash'),
    ]
    payment_method = models.CharField(max_length=10, choices=PAYMENT_METHOD_CHOICES, default='cash')
    insurance_buffer = models.DecimalField(max_digits=10, decimal_places=2, default=0)  # 25% buffer
    deposit = models.DecimalField(max_digits=10, decimal_places=2, default=0)  # 15% deposit
    platform_commission = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    driver_earnings = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    contract_type = models.CharField(max_length=20, choices=[('paper', 'Paper'), ('electronic', 'Electronic')], default='paper')
    contract_signed = models.BooleanField(default=False)
    # --- END NEW FIELDS ---

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)



    def __str__(self):
        return f"Rental #{self.id} - Car {self.car.id} - Renter {self.renter.username} - Status {self.status}"

    


class RentalPayment(models.Model):
    PAYMENT_STATUS_CHOICES = [
        ('Pending', 'Pending'),
        ('Paid', 'Paid'),
        ('Failed', 'Failed'),
    ]

    PAYMENT_METHOD_CHOICES = [
        ('Cash', 'Cash'),
        ('Card', 'Card'),
        ('PayPal', 'PayPal'),
    ]


    rental = models.OneToOneField(Rental, on_delete=models.CASCADE, related_name='payment_info')
    

    deposit_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    deposit_paid_status = models.CharField(max_length=30, choices=PAYMENT_STATUS_CHOICES, default='Pending')
    deposit_paid_at = models.DateTimeField(null=True, blank=True)
    deposit_transaction_id = models.CharField(max_length=100, null=True, blank=True)

    insurance_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    insurance_paid_status = models.CharField(max_length=30, choices=PAYMENT_STATUS_CHOICES, default='Pending')
    insurance_paid_at = models.DateTimeField(null=True, blank=True)
    insurance_transaction_id = models.CharField(max_length=100, null=True, blank=True)

    rental_paid_status = models.CharField(max_length=30, choices=PAYMENT_STATUS_CHOICES, default='Pending')
    rental_paid_at = models.DateTimeField(null=True, blank=True)
    rental_transaction_id = models.CharField(max_length=100, null=True, blank=True)

    payment_method = models.CharField(max_length=10, choices=PAYMENT_METHOD_CHOICES, default='Cash')

    # --- NEW FIELD: Refundable buffer (for wallet/visa) ---
    refundable_buffer = models.DecimalField(max_digits=10, decimal_places=2, default=0)

    def __str__(self):
        return f"Payment info for Rental #{self.rental.id}"


class RentalUsage(models.Model):
    rental = models.OneToOneField(Rental, on_delete=models.CASCADE, related_name='usage_info')

    start_odometer = models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True)
    end_odometer = models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True)
    total_distance_used = models.DecimalField(max_digits=10, decimal_places=2, default=0)

    start_time = models.DateTimeField(null=True, blank=True)
    end_time = models.DateTimeField(null=True, blank=True)
    actual_return_time = models.DateTimeField(null=True, blank=True)

    extra_km = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)  # عدد الكيلومترات الإضافية
    extra_km_charges = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)

    extra_hours = models.DecimalField(max_digits=5, decimal_places=2, default=0.00)  # عدد الساعات الإضافية
    extra_hour_charges = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)  # التكلفة

    # تأكيدات استلام السيارة عند بداية الإيجار
    pickup_confirmed_by_owner = models.BooleanField(default=False, null=True, blank=True)
    pickup_confirmed_by_renter = models.BooleanField(default=False, null=True, blank=True)
    
    # تأكيدات تسليم السيارة عند نهاية الإيجار
    dropoff_confirmed_by_owner = models.BooleanField(default=False, null=True, blank=True)
    dropoff_confirmed_by_renter = models.BooleanField(default=False, null=True, blank=True)
    
    # --- NEW FIELDS FOR WAITING TIME ---
    total_waiting_minutes = models.IntegerField(default=0)
    extra_waiting_minutes = models.IntegerField(default=0)
    waiting_time_cost = models.DecimalField(max_digits=10, decimal_places=2, default=0)

    def __str__(self):
        return f"Usage info for Rental #{self.rental.id}"


class PlannedTrip(models.Model):
    rental = models.OneToOneField(Rental, on_delete=models.CASCADE, related_name='planned_trip')
    route_polyline = models.TextField(null=True, blank=True)

    def __str__(self):
        return f"Planned Trip for Rental #{self.rental.id}"


class PlannedTripStop(models.Model):
    planned_trip = models.ForeignKey(PlannedTrip, on_delete=models.CASCADE, related_name='stops')
    stop_order = models.PositiveIntegerField()
    latitude = models.DecimalField(max_digits=9, decimal_places=6)
    longitude = models.DecimalField(max_digits=9, decimal_places=6)
    approx_waiting_time_minutes = models.PositiveIntegerField(default=0)
    address = models.CharField(max_length=255, null=True, blank=True)  # عنوان المحطة
    is_completed = models.BooleanField(default=False)

    # --- NEW FIELDS FOR ACTUAL WAITING & LOCATION VERIFICATION ---
    actual_waiting_minutes = models.PositiveIntegerField(default=0)
    waiting_started_at = models.DateTimeField(null=True, blank=True)
    waiting_ended_at = models.DateTimeField(null=True, blank=True)
    # For location verification at stop
    location_verified = models.BooleanField(default=False)

    class Meta:
        unique_together = ('planned_trip', 'stop_order')
        ordering = ['stop_order']

    def __str__(self):
        return f"Stop {self.stop_order} for Trip #{self.planned_trip.id}"


class RentalLog(models.Model):
    PERFORMED_BY_CHOICES = [
        ('System', 'System'),
        ('Owner', 'Owner'),
        ('Renter', 'Renter'),
    ]

    rental = models.ForeignKey(Rental, on_delete=models.CASCADE, related_name='logs')
    timestamp = models.DateTimeField(auto_now_add=True)
    event = models.CharField(max_length=255)
    details = models.TextField(null=True, blank=True)
    performed_by_type = models.CharField(max_length=10, choices=PERFORMED_BY_CHOICES, default='System')
    performed_by = models.ForeignKey(User, on_delete=models.CASCADE, null=True, blank=True, related_name='rental_logs')

    def __str__(self):
        return f"[{self.timestamp}] Rental #{self.rental.id} - {self.event}"


class RentalBreakdown(models.Model):
    rental = models.OneToOneField(Rental, on_delete=models.CASCADE, related_name='breakdown')
    planned_km = models.FloatField(default=0)
    total_waiting_minutes = models.IntegerField(default=0)
    daily_price = models.FloatField(default=0)
    extra_km_cost = models.FloatField(default=0)
    waiting_cost = models.FloatField(default=0)
    total_cost = models.FloatField(default=0)
    buffer_amount = models.FloatField(default=0)
    deposit = models.FloatField(default=0)
    platform_fee = models.FloatField(default=0)
    driver_earnings = models.FloatField(default=0)
    allowed_km = models.FloatField(default=0)
    extra_km = models.FloatField(default=0)
    base_cost = models.FloatField(default=0)
    final_cost = models.FloatField(default=0)
    commission_rate = models.FloatField(default=0.2)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Breakdown for Rental #{self.rental.id}"