from django.db import models
from django.contrib.auth import get_user_model
from cars.models import Car

User = get_user_model()

class Rental(models.Model):
    STATUS_CHOICES = [
        ('PendingOwnerConfirmation', 'Pending Owner Confirmation'),
        ('DepositRequired', 'Deposit Required'),
        ('Confirmed', 'Confirmed'),
        ('Ongoing', 'Ongoing'),
        ('Finished', 'Finished'),
        ('Canceled', 'Canceled'),
    ]

    PROPOSED_BY_CHOICES = [('Owner', 'Owner'), ('Renter', 'Renter')]
    renter = models.ForeignKey(User, on_delete=models.CASCADE, related_name='rentals')
    car = models.ForeignKey(Car, on_delete=models.CASCADE, related_name='rentals')
    start_date = models.DateField()
    end_date = models.DateField()
    status = models.CharField(max_length=30, choices=STATUS_CHOICES, default='PendingOwnerConfirmation')
    rental_type = models.CharField(max_length=20, choices=[('WithDriver', 'With Driver'), ('WithoutDriver', 'Without Driver')], default='WithDriver')
    # مواقع التقاط السيارة والتوصيل
    pickup_lat = models.DecimalField(max_digits=15, decimal_places=12, null=True, blank=True)
    pickup_lng = models.DecimalField(max_digits=15, decimal_places=12, null=True, blank=True)
    dropoff_lat = models.DecimalField(max_digits=15, decimal_places=12, null=True, blank=True)
    dropoff_lng = models.DecimalField(max_digits=15, decimal_places=12, null=True, blank=True)
    pickup_address = models.CharField(max_length=255, null=True, blank=True)
    dropoff_address = models.CharField(max_length=255, null=True, blank=True)
    payment_method = models.CharField(max_length=10, choices=[('wallet', 'Wallet'), ('visa', 'Visa/Mastercard'), ('cash', 'Cash')], default='cash')
    
    # Selected card for automatic payments (like self-drive)
    selected_card = models.ForeignKey('payments.SavedCard', on_delete=models.SET_NULL, null=True, blank=True, 
                                     related_name='regular_rentals', 
                                     help_text="Pre-selected card for deposit and remaining payments")
    
    # Owner arrival confirmation
    owner_arrived_at_pickup = models.DateTimeField(null=True, blank=True, help_text="When owner confirmed arrival at pickup location")
    owner_arrival_confirmed = models.BooleanField(default=False, help_text="Whether owner confirmed arrival at pickup location")  # type: ignore
    
    # Renter on the way confirmation
    renter_on_way_announced = models.BooleanField(default=False, help_text="Whether renter announced they are on the way")  # type: ignore
    renter_on_way_announced_at = models.DateTimeField(null=True, blank=True, help_text="When renter announced they are on the way")
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    def __str__(self):
        return f"Rental #{self.id} - Car {self.car.id} - Renter {self.renter.username} - Status {self.status}"  # type: ignore
        

    


class RentalPayment(models.Model):
    PAYMENT_STATUS_CHOICES = [
        ('Pending', 'Pending'),
        ('Paid', 'Paid'),
        ('Failed', 'Failed'),
        ('Refunded', 'Refunded'),
        ('Partially Refunded', 'Partially Refunded'), 
        ('No Remaining to Refund', 'No Remaining to Refund'),
    ]

    PAYMENT_METHOD_CHOICES = [
        ('Cash', 'Cash'),
        ('Card', 'Card'),
        ('PayPal', 'PayPal'),
    ]

    rental = models.OneToOneField(Rental, on_delete=models.CASCADE, related_name='payment_info')

    # 1. Deposit (same as self-drive)
    deposit_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    deposit_paid_status = models.CharField(max_length=30, choices=PAYMENT_STATUS_CHOICES, default='Pending')
    deposit_paid_at = models.DateTimeField(null=True, blank=True)
    deposit_transaction_id = models.CharField(max_length=100, null=True, blank=True)
    deposit_due_at = models.DateTimeField(null=True, blank=True, help_text="Deposit payment deadline (like self-drive)")
    deposit_refunded_status = models.CharField(max_length=30, choices=PAYMENT_STATUS_CHOICES, default='Pending')
    deposit_refunded_at = models.DateTimeField(null=True, blank=True)
    deposit_refund_transaction_id = models.CharField(max_length=100, null=True, blank=True)

    # 2. Remaining Amount
    remaining_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    remaining_paid_status = models.CharField(max_length=30, choices=PAYMENT_STATUS_CHOICES, default='Pending')
    remaining_paid_at = models.DateTimeField(null=True, blank=True)
    remaining_transaction_id = models.CharField(max_length=100, null=True, blank=True)

    # 3. Excess Amount (like self-drive) - for end-of-trip extra charges
    excess_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0, help_text="Extra charges at end of trip")
    excess_paid_status = models.CharField(max_length=30, choices=PAYMENT_STATUS_CHOICES, default='Pending')
    excess_paid_at = models.DateTimeField(null=True, blank=True)
    excess_transaction_id = models.CharField(max_length=100, null=True, blank=True)

    # 3. Limits Excess Insurance
    limits_excess_insurance_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    limits_refunded_status = models.CharField(max_length=30, choices=PAYMENT_STATUS_CHOICES, default='Pending')
    limits_refunded_at = models.DateTimeField(null=True, blank=True)
    limits_refund_transaction_id = models.CharField(max_length=100, null=True, blank=True)

    # 4. All rental
    payment_method = models.CharField(max_length=10, choices=PAYMENT_METHOD_CHOICES, default='Cash')
    rental_total_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0, help_text="Total amount after adding any extra costs at the end of rental")

    def __str__(self):
        return f"Payment info for Rental #{self.rental.id}"  # type: ignore

    @property
    def is_fully_paid(self):
        return (
            self.deposit_paid_status == 'Paid' and
            self.remaining_paid_status == 'Paid'
        )

    @property
    def total_paid_amount(self):
        total = 0
        if self.deposit_paid_status == 'Paid':
            total += self.deposit_amount  # type: ignore
        if self.remaining_paid_status == 'Paid':
            total += self.remaining_amount   # remaining_amount already includes limits_excess_insurance     # type: ignore
        return total

    @property
    def refunded_amount(self):
        total = 0
        if self.deposit_refunded_status == 'Refunded':
            total += self.deposit_amount  # type: ignore
        if self.limits_refunded_status == 'Refunded':
            total += self.limits_excess_insurance_amount  # type: ignore
        return total

    @property
    def limits_status(self):
        if not self.limits_excess_insurance_amount:
            return 'Not Required'
        if self.limits_refunded_status == 'Refunded':
            return 'Refunded'
        if self.remaining_paid_status == 'Paid' and not self.limits_refunded_at:
            return 'Pending Refund'
        return 'Pending'

    


class PlannedTrip(models.Model):
    rental = models.OneToOneField(Rental, on_delete=models.CASCADE, related_name='planned_trip')
    route_polyline = models.TextField(null=True, blank=True)

    def __str__(self):
        return f"Planned Trip for Rental #{self.rental.id}"  # type: ignore


class PlannedTripStop(models.Model):
    planned_trip = models.ForeignKey(PlannedTrip, on_delete=models.CASCADE, related_name='stops')
    stop_order = models.PositiveIntegerField()
    latitude = models.DecimalField(max_digits=9, decimal_places=6)
    longitude = models.DecimalField(max_digits=9, decimal_places=6)
    approx_waiting_time_minutes = models.PositiveIntegerField(default=0)  # type: ignore
    address = models.CharField(max_length=255, null=True, blank=True)  # عنوان المحطة
    is_completed = models.BooleanField(default=False)  # type: ignore

    # --- NEW FIELDS FOR ACTUAL WAITING & LOCATION VERIFICATION ---
    actual_waiting_minutes = models.PositiveIntegerField(default=0)  # type: ignore
    waiting_started_at = models.DateTimeField(null=True, blank=True)
    waiting_ended_at = models.DateTimeField(null=True, blank=True)
    # For location verification at stop
    location_verified = models.BooleanField(default=False)  # type: ignore

    class Meta:
        unique_together = ('planned_trip', 'stop_order')
        ordering = ['stop_order']

    def __str__(self):
        return f"Stop {self.stop_order} for Trip #{self.planned_trip.id}"  # type: ignore


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
        return f"[{self.timestamp}] Rental #{self.rental.id} - {self.event}"  # type: ignore


class RentalBreakdown(models.Model):
    rental = models.OneToOneField(Rental, on_delete=models.CASCADE, related_name='breakdown')
    
    # ===== INITIAL PLANNING =====
    planned_km = models.FloatField(default=0)  # type: ignore
    total_waiting_minutes = models.IntegerField(default=0, help_text="Planned waiting minutes")  # type: ignore
    daily_price = models.FloatField(default=0)  # type: ignore
    
    # ===== BASIC COSTS =====
    extra_km_cost = models.FloatField(default=0)  # type: ignore
    waiting_cost = models.FloatField(default=0)  # type: ignore
    total_cost = models.FloatField(default=0)  # type: ignore
    deposit = models.FloatField(default=0)  # type: ignore
    platform_fee = models.FloatField(default=0)  # type: ignore
    driver_earnings = models.FloatField(default=0)  # type: ignore
    allowed_km = models.FloatField(default=0)  # type: ignore
    extra_km = models.FloatField(default=0)  # type: ignore
    base_cost = models.FloatField(default=0)  # type: ignore
    final_cost = models.FloatField(default=0, help_text="Final cost without end-of-trip excess")  # type: ignore
    commission_rate = models.FloatField(default=0.2)  # type: ignore
    
    # ===== END-OF-TRIP EXCESS (like self-drive) =====
    actual_total_waiting_minutes = models.IntegerField(default=0, help_text="Actual waiting minutes at end of trip")  # type: ignore
    extra_waiting_minutes = models.IntegerField(default=0, help_text="Extra waiting beyond planned")  # type: ignore
    excess_waiting_cost = models.FloatField(default=0, help_text="Cost of extra waiting")  # type: ignore
    
    # ===== FINAL TOTALS =====
    final_total_cost = models.FloatField(default=0, help_text="Final cost including all excess charges")  # type: ignore
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Breakdown for Rental #{self.rental.id}"  # type: ignore
        
    @property
    def has_excess_charges(self):
        """Check if there are any excess charges"""
        return self.excess_waiting_cost > 0
        
    @property
    def excess_summary(self):
        """Summary of excess charges"""
        if not self.has_excess_charges:
            return {"message": "No excess charges"}
        
        return {
            "extra_waiting_minutes": self.extra_waiting_minutes,
            "excess_waiting_cost": self.excess_waiting_cost,
            "original_cost": self.final_cost,
            "final_total_cost": self.final_total_cost,
            "message": f"Extra {self.extra_waiting_minutes} minutes = {self.excess_waiting_cost} EGP"
        }