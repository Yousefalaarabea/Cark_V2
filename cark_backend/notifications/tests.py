from django.test import TestCase
from django.contrib.auth import get_user_model
from django.utils import timezone
from datetime import timedelta
from notifications.models import Notification
from notifications.services import NotificationService
from selfdrive_rentals.models import SelfDriveRental, SelfDrivePayment, SelfDriveRentalBreakdown, SelfDriveContract
from cars.models import Car, CarRentalOptions, CarUsagePolicy

User = get_user_model()

class NotificationServiceTestCase(TestCase):
    def setUp(self):
        """Set up test data"""
        # Create test users
        self.owner = User.objects.create_user(
            email='owner@test.com',
            password='testpass123',
            first_name='John',
            last_name='Owner'
        )
        
        self.renter = User.objects.create_user(
            email='renter@test.com',
            password='testpass123',
            first_name='Jane',
            last_name='Renter'
        )
        
        # Create test car
        self.car = Car.objects.create( # type: ignore
            owner=self.owner,
            model='Camry',
            brand='Toyota',
            car_type='Sedan',
            car_category='Economy',
            plate_number='ABC123',
            year=2020,
            color='White',
            seating_capacity=5,
            transmission_type='Automatic',
            fuel_type='Petrol',
            current_odometer_reading=50000,
            approval_status=True
        )
        
        # Create rental options
        CarRentalOptions.objects.create( # type: ignore
            car=self.car,
            available_without_driver=True,
            daily_rental_price=200.00
        )
        
        # Create usage policy
        CarUsagePolicy.objects.create( # type: ignore   
            car=self.car,
            daily_km_limit=200.00,
            extra_km_cost=2.00
        )
        
        # Create test rental
        self.rental = SelfDriveRental.objects.create( # type: ignore
            renter=self.renter,
            car=self.car,
            start_date=timezone.now() + timedelta(days=1),
            end_date=timezone.now() + timedelta(days=3),
            pickup_address='Cairo, Egypt',
            dropoff_address='Alexandria, Egypt',
            status='PendingOwnerConfirmation'
        )
        
        # Create payment
        SelfDrivePayment.objects.create( # type: ignore
            rental=self.rental,
            deposit_amount=60.00,
            remaining_amount=540.00,
            rental_total_amount=600.00
        )
        
        # Create breakdown
        SelfDriveRentalBreakdown.objects.create( # type: ignore
            rental=self.rental,
            num_days=3,
            daily_price=200.00,
            base_cost=600.00,
            initial_cost=600.00,
            final_cost=600.00
        )
        
        # Create contract
        SelfDriveContract.objects.create(rental=self.rental) # type: ignore
    
    def test_send_booking_request_notification(self):
        """Test sending booking request notification"""
        # Send notification
        notification = NotificationService.send_booking_request_notification(self.rental)
        
        # Verify notification was created
        self.assertIsNotNone(notification)
        self.assertEqual(notification.receiver, self.owner) # type: ignore
        self.assertEqual(notification.sender, self.renter) # type: ignore
        self.assertEqual(notification.title, "New Booking Request") # type: ignore
        self.assertEqual(notification.notification_type, "RENTAL") # type: ignore
        self.assertEqual(notification.priority, "HIGH") # type: ignore
        self.assertFalse(notification.is_read) # type: ignore
        
        # Verify notification data
        self.assertIn('renterId', notification.data) # type: ignore
        self.assertIn('carId', notification.data) # type: ignore
        self.assertIn('rentalId', notification.data) # type: ignore
        self.assertIn('renterName', notification.data) # type: ignore
        self.assertIn('carName', notification.data) # type: ignore
        self.assertEqual(notification.data['renterId'], self.renter.id) # type: ignore
        self.assertEqual(notification.data['carId'], self.car.id) # type: ignore
        self.assertEqual(notification.data['rentalId'], self.rental.id) # type: ignore
        self.assertEqual(notification.data['renterName'], 'Jane Renter') # type: ignore
        self.assertEqual(notification.data['carName'], 'Toyota Camry') # type: ignore
    
    def test_send_status_update_notification(self):
        """Test sending status update notification"""
        # Send notification
        notification = NotificationService.send_rental_status_update_notification(
            rental=self.rental,
            old_status='PendingOwnerConfirmation',
            new_status='Confirmed',
            updated_by=self.owner
        )
        
        # Verify notification was created
        self.assertIsNotNone(notification)
        self.assertEqual(notification.receiver, self.renter) # type: ignore
        self.assertEqual(notification.sender, self.owner) # type: ignore
        self.assertEqual(notification.title, "Rental Status Update - Confirmed") # type: ignore
        self.assertEqual(notification.notification_type, "RENTAL") # type: ignore
        self.assertEqual(notification.priority, "NORMAL") # type: ignore
        
        # Verify notification data
        self.assertIn('rentalId', notification.data) # type: ignore
        self.assertIn('oldStatus', notification.data) # type: ignore
        self.assertIn('newStatus', notification.data) # type: ignore
        self.assertEqual(notification.data['oldStatus'], 'PendingOwnerConfirmation') # type: ignore
        self.assertEqual(notification.data['newStatus'], 'Confirmed') # type: ignore
    
    def test_send_payment_notification(self):
        """Test sending payment notification"""
        # Send notification
        notification = NotificationService.send_payment_notification(
            rental=self.rental,
            payment_type='deposit',
            amount=60.00,
            status='Paid'
        )
        
        # Verify notification was created
        self.assertIsNotNone(notification)
        self.assertEqual(notification.receiver, self.owner) # type: ignore
        self.assertEqual(notification.sender, self.renter) # type: ignore
        self.assertEqual(notification.title, "Payment Paid") # type: ignore
        self.assertEqual(notification.notification_type, "PAYMENT") # type: ignore
        self.assertEqual(notification.priority, "HIGH") # type: ignore
        
        # Verify notification data
        self.assertIn('rentalId', notification.data) # type: ignore
        self.assertIn('paymentType', notification.data) # type: ignore
        self.assertIn('amount', notification.data) # type: ignore
        self.assertEqual(notification.data['paymentType'], 'deposit') # type: ignore
        self.assertEqual(notification.data['amount'], 60.00) # type: ignore
