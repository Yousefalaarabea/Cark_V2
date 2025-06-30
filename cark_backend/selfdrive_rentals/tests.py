from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APIClient
from django.contrib.auth import get_user_model
from cars.models import Car
from .models import SelfDriveRental, SelfDriveOdometerImage, SelfDriveContract, SelfDriveRentalBreakdown, SelfDrivePayment
from django.utils import timezone

User = get_user_model()

class SelfDriveRentalFlowTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(username='renter', password='testpass')
        self.owner = User.objects.create_user(username='owner', password='testpass')
        self.car = Car.objects.create(model='TestCar', daily_rental_price=100, ctw_fee=20, extra_km_cost=2)
        self.client.force_authenticate(user=self.user)
        self.rental = SelfDriveRental.objects.create(
            renter=self.user, car=self.car,
            start_date=timezone.now(), end_date=timezone.now() + timezone.timedelta(days=2),
            pickup_location='A', dropoff_location='B', status='Pending', daily_km_limit=200
        )
        SelfDriveContract.objects.create(rental=self.rental)

    def test_cannot_start_trip_without_odometer_or_contract(self):
        url = reverse('selfdriverental-start-trip', args=[self.rental.id])
        # بدون صورة عداد وتوقيع عقد
        response = self.client.post(url)
        self.assertEqual(response.status_code, 400)
        # أضف صورة عداد فقط
        SelfDriveOdometerImage.objects.create(rental=self.rental, value=1000, image='img.jpg', type='start')
        response = self.client.post(url)
        self.assertEqual(response.status_code, 400)
        # وقع العقد من الطرفين
        contract = self.rental.contract
        contract.signed_by_renter = True
        contract.signed_by_owner = True
        contract.save()
        response = self.client.post(url)
        self.assertEqual(response.status_code, 200)
        self.rental.refresh_from_db()
        self.assertEqual(self.rental.status, 'Ongoing')

    def test_cannot_end_trip_without_end_odometer(self):
        self.rental.status = 'Ongoing'
        self.rental.save()
        url = reverse('selfdriverental-end-trip', args=[self.rental.id])
        response = self.client.post(url)
        self.assertEqual(response.status_code, 400)
        # أضف صورة عداد نهاية
        SelfDriveOdometerImage.objects.create(rental=self.rental, value=1200, image='img2.jpg', type='end')
        response = self.client.post(url)
        self.assertEqual(response.status_code, 200)
        self.rental.refresh_from_db()
        self.assertEqual(self.rental.status, 'Finished')

    def test_breakdown_and_payment_calculation(self):
        # إعداد الرحلة كاملة
        SelfDriveOdometerImage.objects.create(rental=self.rental, value=1000, image='img.jpg', type='start')
        contract = self.rental.contract
        contract.signed_by_renter = True
        contract.signed_by_owner = True
        contract.save()
        self.rental.status = 'Ongoing'
        self.rental.save()
        SelfDriveOdometerImage.objects.create(rental=self.rental, value=1500, image='img2.jpg', type='end')
        url = reverse('selfdriverental-end-trip', args=[self.rental.id])
        self.client.post(url)
        self.rental.refresh_from_db()
        breakdown = self.rental.breakdown
        payment = self.rental.payment
        self.assertIsNotNone(breakdown)
        self.assertIsNotNone(payment)
        self.assertGreaterEqual(breakdown.final_cost, 0)
        self.assertEqual(payment.rental_total_amount, breakdown.final_cost)

    def test_simulate_payment(self):
        # إعداد الرحلة كاملة
        SelfDriveOdometerImage.objects.create(rental=self.rental, value=1000, image='img.jpg', type='start')
        contract = self.rental.contract
        contract.signed_by_renter = True
        contract.signed_by_owner = True
        contract.save()
        self.rental.status = 'Ongoing'
        self.rental.save()
        SelfDriveOdometerImage.objects.create(rental=self.rental, value=1500, image='img2.jpg', type='end')
        url = reverse('selfdriverental-end-trip', args=[self.rental.id])
        self.client.post(url)
        pay_url = reverse('selfdriverental-simulate-payment', args=[self.rental.id])
        response = self.client.post(pay_url)
        self.assertEqual(response.status_code, 200)
        self.rental.payment.refresh_from_db()
        self.assertEqual(self.rental.payment.remaining_paid_status, 'Paid')
