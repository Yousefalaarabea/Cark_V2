from django.db import models
from django.contrib.auth import get_user_model
from cars.models import Car
from payments.models import SavedCard

User = get_user_model()

class SelfDriveRental(models.Model):
    STATUS_CHOICES = [
        ('Pending', 'Pending'),
        ('PendingOwnerConfirmation', 'PendingOwnerConfirmation'),
        ('Confirmed', 'Confirmed'),
        ('Ongoing', 'Ongoing'),
        ('Finished', 'Finished'),
        ('Canceled', 'Canceled'),
    ]
    renter = models.ForeignKey(User, on_delete=models.CASCADE, related_name='selfdrive_rentals')
    car = models.ForeignKey(Car, on_delete=models.CASCADE, related_name='selfdrive_rentals')
    start_date = models.DateTimeField()
    end_date = models.DateTimeField()
    pickup_address = models.CharField(max_length=255)
    dropoff_address = models.CharField(max_length=255)
    pickup_latitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    pickup_longitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    dropoff_latitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    dropoff_longitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    status = models.CharField(max_length=32, choices=STATUS_CHOICES, default='Pending')
    selected_card = models.ForeignKey(SavedCard, null=True, blank=True, on_delete=models.SET_NULL, related_name='selfdrive_rentals')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"SelfDriveRental #{self.id} - {self.car} - {self.renter}"

class SelfDriveOdometerImage(models.Model):
    ODOMETER_TYPE_CHOICES = [
        ('start', 'Start'),
        ('end', 'End'),
    ]
    rental = models.ForeignKey(SelfDriveRental, on_delete=models.CASCADE, related_name='odometer_images')
    image = models.ImageField(upload_to='selfdrive/odometers/')
    value = models.FloatField(help_text='Odometer reading at this point')
    type = models.CharField(max_length=10, choices=ODOMETER_TYPE_CHOICES)
    uploaded_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Odometer {self.type} for Rental #{self.rental.id}"

class SelfDriveContract(models.Model):
    rental = models.OneToOneField(SelfDriveRental, on_delete=models.CASCADE, related_name='contract')
    renter_signed = models.BooleanField(default=False)
    renter_signed_at = models.DateTimeField(null=True, blank=True)
    owner_signed = models.BooleanField(default=False)
    owner_signed_at = models.DateTimeField(null=True, blank=True)
    contract_pdf = models.FileField(upload_to='contracts/', null=True, blank=True)
    owner_contract_image = models.ImageField(upload_to='contracts/owner_signed/', null=True, blank=True)
    renter_pickup_done = models.BooleanField(default=False)
    renter_pickup_done_at = models.DateTimeField(null=True, blank=True)
    owner_pickup_done = models.BooleanField(default=False)
    owner_pickup_done_at = models.DateTimeField(null=True, blank=True)
    renter_return_done = models.BooleanField(default=False)
    renter_return_done_at = models.DateTimeField(null=True, blank=True)
    owner_return_done = models.BooleanField(default=False)
    owner_return_done_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Contract for Rental #{self.rental.id} | Renter: {'✔' if self.renter_signed else '✗'} | Owner: {'✔' if self.owner_signed else '✗'}"

class SelfDriveLiveLocation(models.Model):
    rental = models.ForeignKey(SelfDriveRental, on_delete=models.CASCADE, related_name='live_locations')
    latitude = models.DecimalField(max_digits=9, decimal_places=6)
    longitude = models.DecimalField(max_digits=9, decimal_places=6)
    timestamp = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Location for Rental #{self.rental.id} at {self.timestamp}"

class SelfDrivePayment(models.Model):
    rental = models.OneToOneField('SelfDriveRental', on_delete=models.CASCADE, related_name='payment')

    # Deposit
    deposit_amount = models.FloatField(default=0)
    deposit_paid_status = models.CharField(max_length=16, choices=[('Pending', 'Pending'), ('Paid', 'Paid'), ('Refunded', 'Refunded')], default='Pending')
    deposit_paid_at = models.DateTimeField(null=True, blank=True)
    deposit_transaction_id = models.CharField(max_length=128, null=True, blank=True)
    deposit_refunded = models.BooleanField(default=False)
    deposit_refunded_at = models.DateTimeField(null=True, blank=True)
    deposit_refund_transaction_id = models.CharField(max_length=128, null=True, blank=True)
    deposit_due_at = models.DateTimeField(null=True, blank=True)

    # Remaining (to be paid at start)
    remaining_amount = models.FloatField(default=0)
    remaining_paid_status = models.CharField(max_length=16, choices=[('Pending', 'Pending'), ('Paid', 'Paid'), ('Confirmed', 'Confirmed')], default='Pending')
    remaining_paid_at = models.DateTimeField(null=True, blank=True)
    remaining_transaction_id = models.CharField(max_length=128, null=True, blank=True)

    # Excess (to be paid at end)
    excess_amount = models.FloatField(default=0)
    excess_paid_status = models.CharField(max_length=16, choices=[('Pending', 'Pending'), ('Paid', 'Paid')], default='Pending')
    excess_paid_at = models.DateTimeField(null=True, blank=True)
    excess_transaction_id = models.CharField(max_length=128, null=True, blank=True)

    # Payment method and total
    payment_method = models.CharField(max_length=16, choices=[('visa', 'Visa'), ('wallet', 'Wallet'), ('cash', 'Cash')], default='cash')
    rental_total_amount = models.FloatField(default=0)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Payment for SelfDriveRental #{self.rental.id}"

class SelfDriveRentalBreakdown(models.Model):
    rental = models.OneToOneField(SelfDriveRental, on_delete=models.CASCADE, related_name='breakdown')
    actual_dropoff_time = models.DateTimeField(null=True, blank=True, help_text='Actual dropoff time recorded at end of rental')

    # Initial rental parameters
    num_days = models.PositiveIntegerField(default=1)
    daily_price = models.FloatField(default=0)
    
    # Initial costs
    base_cost = models.FloatField(default=0)
    ctw_fee = models.FloatField(default=0)
    initial_cost = models.FloatField(default=0)

    # KM usage
    allowed_km = models.FloatField(default=0)
    extra_km = models.FloatField(default=0)
    extra_km_cost = models.FloatField(default=0)
    extra_km_fee = models.FloatField(default=0)

    # Late return
    late_days = models.PositiveIntegerField(default=0)
    late_fee = models.FloatField(default=0)

    # Totals
    total_extras_cost = models.FloatField(default=0)
    final_cost = models.FloatField(default=0)

    # Earnings
    commission_rate = models.FloatField(default=0.2)
    platform_earnings = models.FloatField(default=0)
    driver_earnings = models.FloatField(default=0)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Breakdown for SelfDriveRental #{self.rental.id}"

class SelfDriveRentalLog(models.Model):
    ACTION_CHOICES = [
        ('create_rental', 'Create Rental'),
        ('owner_confirm', 'Owner Confirm'),
        ('deposit_paid', 'Deposit Paid'),
        ('owner_pickup_handover', 'Owner Pickup Handover'),
        ('renter_pickup_handover', 'Renter Pickup Handover'),
        ('trip_started', 'Trip Started'),
        ('location_requested', 'Location Requested'),
        ('renter_dropoff_handover', 'Renter Dropoff Handover'),
        ('owner_dropoff_handover', 'Owner Dropoff Handover'),
        ('trip_finished', 'Trip Finished'),
        ('canceled', 'Canceled'),
        # أضف المزيد حسب الحاجة
    ]
    rental = models.ForeignKey('SelfDriveRental', on_delete=models.CASCADE, related_name='logs')
    action = models.CharField(max_length=32, choices=ACTION_CHOICES)
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    timestamp = models.DateTimeField(auto_now_add=True)
    details = models.TextField(blank=True, null=True)

    def __str__(self):
        return f"{self.get_action_display()} by {self.user} at {self.timestamp}"

class SelfDriveRentalStatusHistory(models.Model):
    rental = models.ForeignKey('SelfDriveRental', on_delete=models.CASCADE, related_name='status_history')
    old_status = models.CharField(max_length=32)
    new_status = models.CharField(max_length=32)
    changed_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    timestamp = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.old_status} → {self.new_status} at {self.timestamp}"

class SelfDriveCarImage(models.Model):
    rental = models.ForeignKey('SelfDriveRental', on_delete=models.CASCADE, related_name='car_images')
    image = models.ImageField(upload_to='car_images/')
    type = models.CharField(max_length=10, choices=[('pickup', 'Pickup'), ('return', 'Return')])
    uploaded_by = models.CharField(max_length=10, choices=[('renter', 'Renter'), ('owner', 'Owner')])
    uploaded_at = models.DateTimeField(auto_now_add=True)
    notes = models.TextField(blank=True, null=True)
    def __str__(self):
        return f"CarImage {self.type} by {self.uploaded_by} for rental #{self.rental.id}"