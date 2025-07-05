from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from .models import SelfDriveRental, SelfDriveOdometerImage, SelfDriveContract, SelfDriveLiveLocation, SelfDrivePayment, SelfDriveRentalBreakdown, SelfDriveRentalLog, SelfDriveRentalStatusHistory, SelfDriveCarImage
from .serializers import (
    SelfDriveRentalSerializer, SelfDriveOdometerImageSerializer, SelfDriveContractSerializer,
    SelfDriveLiveLocationSerializer, SelfDrivePaymentSerializer, SelfDriveRentalBreakdownSerializer
)
from django.utils import timezone
from django.db import transaction
from django.shortcuts import get_object_or_404
from rest_framework.exceptions import ValidationError
from .services import calculate_selfdrive_financials
import math
from django.core.files.base import ContentFile
import base64
from datetime import timedelta
from payments.services.payment_gateway import simulate_payment_gateway
from wallets.models import Wallet, WalletTransaction, TransactionType
from decimal import Decimal
from payments.services import paymob
from payments.models import SavedCard
from django.conf import settings
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated
from notifications.services import NotificationService

import random
from cars.models import Car


class SelfDriveRentalViewSet(viewsets.ModelViewSet):
    queryset = SelfDriveRental.objects.all()  # type: ignore
    serializer_class = SelfDriveRentalSerializer

    def perform_create(self, serializer):
        with transaction.atomic():  # type: ignore
            rental = serializer.save(renter=self.request.user)
            duration_days = (rental.end_date.date() - rental.start_date.date()).days + 1
            options = getattr(rental.car, 'rental_options', None)
            if not options:
                raise ValidationError("rental_options must be set for the car.")
            policy = getattr(rental.car, 'usage_policy', None)
            if not policy:
                raise ValidationError("usage_policy must be set for the car.")
            daily_km_limit = getattr(policy, 'daily_km_limit', None)
            if daily_km_limit is None:
                raise ValidationError("daily_km_limit must be set in car usage policy.")
            extra_km_cost = getattr(policy, 'extra_km_cost', None)
            if extra_km_cost is None:
                raise ValidationError("extra_km_cost must be set in car usage policy.")
            daily_rental_price = getattr(options, 'daily_rental_price', None)
            if daily_rental_price is None:
                raise ValidationError("daily_rental_price must be set in car rental options.")
            financials = calculate_selfdrive_financials(daily_rental_price, duration_days)
            allowed_km = duration_days * float(daily_km_limit)
            rental.save()
            rental.status = 'PendingOwnerConfirmation'
            rental.save()
            commission_rate = 0.2
            initial_cost = financials['final_cost']
            platform_earnings = initial_cost * commission_rate
            driver_earnings = initial_cost - platform_earnings
            SelfDriveRentalBreakdown.objects.create(  # type: ignore
                rental=rental,
                num_days=duration_days,
                daily_price=daily_rental_price,
                allowed_km=allowed_km,
                base_cost=financials['base_cost'],
                ctw_fee=financials['ctw_fee'],
                initial_cost=initial_cost,
                extra_km_cost=extra_km_cost,
                extra_km=0,
                extra_km_fee=0,
                late_days=0,
                late_fee=0,
                total_extras_cost=0,
                final_cost=initial_cost,
                commission_rate=commission_rate,
                platform_earnings=platform_earnings,
                driver_earnings=driver_earnings
            )
            payment_method = getattr(rental, '_payment_method', 'Cash')
            deposit_amount = round(initial_cost * 0.15, 2)
            remaining_amount = round(initial_cost - deposit_amount, 2)
            SelfDrivePayment.objects.create(  # type: ignore
                rental=rental,
                deposit_amount=deposit_amount,
                deposit_paid_status='Pending',
                remaining_amount=remaining_amount,
                remaining_paid_status='Pending',
                payment_method=payment_method,
                rental_total_amount=initial_cost
            )
            SelfDriveContract.objects.create(rental=rental)  # type: ignore
            
            # Send booking request notification to car owner
            try:
                from notifications.models import Notification
                
                # Get renter details
                renter_name = f"{rental.renter.first_name} {rental.renter.last_name}".strip() or rental.renter.email
                car_name = f"{rental.car.brand} {rental.car.model}"
                
                # Create notification data
                notification_data = {
                    "renterId": rental.renter.id,
                    "carId": rental.car.id,
                    "status": rental.status,
                    "rentalId": rental.id,
                    "startDate": rental.start_date.isoformat(),
                    "endDate": rental.end_date.isoformat(),
                    "pickupAddress": rental.pickup_address,
                    "dropoffAddress": rental.dropoff_address,
                    "renterName": renter_name,
                    "carName": car_name,
                    "dailyPrice": float(rental.car.rental_options.daily_rental_price) if rental.car.rental_options.daily_rental_price else 0,
                    "totalDays": (rental.end_date.date() - rental.start_date.date()).days + 1,
                    "totalAmount": float(rental.payment.rental_total_amount) if hasattr(rental, 'payment') else 0,
                    "depositAmount": float(rental.payment.deposit_amount) if hasattr(rental, 'payment') else 0,
                }
                
                # Create notification
                notification = Notification.objects.create(  # type: ignore
                
                    sender=rental.renter,  # Renter is the sender
                    receiver=rental.car.owner,    # Car owner is the receiver
                    title="New Booking Request",
                    message=f"{renter_name} has requested to rent your {car_name}",
                    notification_type="RENTAL",
                    priority="HIGH",
                    data=notification_data,
                    navigation_id="REQ_OWNER",
                    is_read=False
                )
            except Exception as e:
                print(f"Error sending booking request notification: {str(e)}")

    @action(detail=True, methods=['post'])
    def upload_odometer(self, request, pk=None):
        rental = self.get_object()
        serializer = SelfDriveOdometerImageSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save(rental=rental)
            return Response(serializer.data, status=201)
        return Response(serializer.errors, status=400)

    @action(detail=True, methods=['post'])
    def sign_contract(self, request, pk=None):
        rental = self.get_object()
        contract, created = SelfDriveContract.objects.get_or_create(rental=rental)
        signer = request.data.get('signer')
        if signer == 'renter':
            contract.signed_by_renter = True
        elif signer == 'owner':
            contract.signed_by_owner = True
        else:
            return Response({'error': 'Invalid signer.'}, status=400)
        contract.signed_at = timezone.now()
        contract.save()
        return Response(SelfDriveContractSerializer(contract).data)

    @action(detail=True, methods=['post'])
    def add_location(self, request, pk=None):
        rental = self.get_object()
        serializer = SelfDriveLiveLocationSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save(rental=rental)
            return Response(serializer.data, status=201)
        return Response(serializer.errors, status=400)

    @action(detail=True, methods=['post'])
    def end_trip(self, request, pk=None):
        rental = self.get_object()
        payment = rental.payment
        has_end_odometer = rental.odometer_images.filter(type='end').exists()
        if not has_end_odometer:
            return Response({'error_code': 'ODOMETER_END_REQUIRED', 'error_message': 'يجب رفع صورة عداد النهاية وقراءة العداد قبل إنهاء الرحلة.'}, status=400)
        # حساب الزيادات
        actual_dropoff_time = timezone.now()
        try:
            payment = calculate_selfdrive_payment(rental, actual_dropoff_time=actual_dropoff_time)
        except ValueError as e:
            return Response({'error_code': 'INVALID_DATA', 'error_message': str(e)}, status=400)
        if payment.excess_amount > 0 and payment.excess_paid_status != 'Paid':
            if payment.payment_method in ['visa', 'wallet']:
                payment_response = simulate_payment_gateway(
                    amount=payment.excess_amount,
                    payment_method=payment.payment_method,
                    user=request.user
                )
                if payment_response.success:
                    payment.excess_paid_status = 'Paid'
                    payment.excess_paid_at = timezone.now()
                    payment.excess_transaction_id = payment_response.transaction_id
                    payment.save()
                    from .models import SelfDriveRentalLog
                    SelfDriveRentalLog.objects.create(
                        rental=payment.rental,
                        action='payment',
                        user=request.user,
                        details=f'Excess payment: {payment_response.transaction_id}'
                    )
                else:
                    return Response({'error_code': 'EXCESS_PAYMENT_FAILED', 'error_message': payment_response.message}, status=400)
            else:
                return Response({'error_code': 'EXCESS_REQUIRED', 'error_message': 'يجب دفع الزيادات إلكترونياً قبل إنهاء الرحلة.'}, status=400)
        old_status = rental.status
        rental.status = 'Finished'
        rental.save()
        SelfDriveRentalLog.objects.create(rental=rental, action='end_trip', user=request.user, details='Trip ended by user.')
        SelfDriveRentalStatusHistory.objects.create(rental=rental, old_status=old_status, new_status='Finished', changed_by=request.user)
        return Response(SelfDrivePaymentSerializer(payment).data)

    @action(detail=True, methods=['post'])
    def start_trip(self, request, pk=None):
        rental = self.get_object()
        contract = rental.contract
        payment = rental.payment
        if not (contract.renter_pickup_done and contract.owner_pickup_done and contract.renter_signed and contract.owner_signed):
            return Response({'error_code': 'REQUIREMENTS_NOT_MET', 'error_message': 'يجب إتمام التسليم والتوقيع من الطرفين قبل بدء الرحلة.'}, status=400)
        if payment.deposit_paid_status != 'Paid':
            return Response({'error_code': 'DEPOSIT_REQUIRED', 'error_message': 'يجب دفع العربون قبل بدء الرحلة.'}, status=400)
        if payment.payment_method in ['visa', 'wallet'] and payment.remaining_paid_status != 'Paid':
                return Response({'error_code': 'REMAINING_REQUIRED', 'error_message': 'يجب دفع باقي المبلغ إلكترونياً قبل بدء الرحلة.'}, status=400)
        if payment.payment_method == 'cash' and payment.remaining_paid_status != 'Confirmed':
            return Response({'error_code': 'REMAINING_CASH_CONFIRM', 'error_message': 'يجب تأكيد استلام باقي المبلغ كاش قبل بدء الرحلة.'}, status=400)
        if rental.status == 'Ongoing':
            return Response({'error_code': 'ALREADY_STARTED', 'error_message': 'تم بدء الرحلة بالفعل.'}, status=400)
        old_status = rental.status
        rental.status = 'Ongoing'
        rental.save()
        SelfDriveRentalLog.objects.create(rental=rental, action='trip_started', user=request.user, details='Trip started by renter.')
        SelfDriveRentalStatusHistory.objects.create(rental=rental, old_status=old_status, new_status='Ongoing', changed_by=request.user)
        return Response({'status': 'تم بدء الرحلة.'})

    @action(detail=True, methods=['get'])
    def invoice(self, request, pk=None):
        rental = self.get_object()
        breakdown = None
        payment = None
        excess_details = None
        if hasattr(rental, 'breakdown'):
            breakdown = SelfDriveRentalBreakdownSerializer(rental.breakdown).data
            # Build excess details
            excess_details = {
                'excess_amount': rental.breakdown.extra_km_fee + rental.breakdown.late_fee,
                'extra_km_fee': rental.breakdown.extra_km_fee,
                'late_fee': rental.breakdown.late_fee,
                'extra_km': rental.breakdown.extra_km,
                'extra_km_cost': rental.breakdown.extra_km_cost,
                'late_days': rental.breakdown.late_days,
                'late_fee_per_day': rental.breakdown.daily_price,
                'late_fee_service_percent': 30,
            }
        if hasattr(rental, 'payment'):
            payment = SelfDrivePaymentSerializer(rental.payment).data
        return Response({
            'breakdown': breakdown,
            'payment': payment,
            'excess_details': excess_details
        })

    @action(detail=True, methods=['post'])
    def confirm_handover(self, request, pk=None):
        rental = self.get_object()
        if rental.status != 'Pending':
            return Response({'error_code': 'INVALID_STATUS', 'error_message': 'لا يمكن تأكيد التسليم إلا إذا كانت الرحلة في حالة Pending.'}, status=400)
        payment = rental.payment
        if payment.deposit_paid_status != 'Paid':
            return Response({'error_code': 'DEPOSIT_REQUIRED', 'error_message': 'يجب دفع الديبوزيت قبل تأكيد التسليم.'}, status=400)
        old_status = rental.status
        rental.status = 'Confirmed'
        rental.save()
        SelfDriveRentalLog.objects.create(rental=rental, action='confirm_handover', user=request.user, details='Handover confirmed.')
        SelfDriveRentalStatusHistory.objects.create(rental=rental, old_status=old_status, new_status='Confirmed', changed_by=request.user)
        return Response({'status': 'Handover confirmed.'})

    @action(detail=True, methods=['post'])
    def change_status(self, request, pk=None):
        rental = self.get_object()
        new_status = request.data.get('status')
        allowed_statuses = ['Pending', 'Confirmed', 'Ongoing', 'Finished', 'Canceled']
        if new_status not in allowed_statuses:
            return Response({'error_code': 'INVALID_STATUS', 'error_message': 'الحالة غير مسموحة. الحالات المسموحة: Pending, Confirmed, Ongoing, Finished, Canceled.'}, status=400)
        if new_status == 'Ongoing':
            has_start_odometer = rental.odometer_images.filter(type='start').exists()
            if not has_start_odometer:
                return Response({'error_code': 'ODOMETER_START_REQUIRED', 'error_message': 'يجب رفع صورة عداد البداية قبل بدء الرحلة.'}, status=400)
            if not hasattr(rental, 'contract') or not (rental.contract.renter_signed and rental.contract.owner_signed):
                return Response({'error_code': 'CONTRACT_NOT_SIGNED', 'error_message': 'يجب توقيع العقد من الطرفين قبل بدء الرحلة.'}, status=400)
        if new_status == 'Finished':
            has_end_odometer = rental.odometer_images.filter(type='end').exists()
            if not has_end_odometer:
                return Response({'error_code': 'ODOMETER_END_REQUIRED', 'error_message': 'يجب رفع صورة عداد النهاية وقراءة العداد قبل إنهاء الرحلة.'}, status=400)
            if not hasattr(rental, 'payment') or rental.payment.remaining_paid_status != 'Paid':
                return Response({'error_code': 'PAYMENT_REQUIRED', 'error_message': 'يجب دفع الفاتورة قبل إنهاء الرحلة.'}, status=400)
        old_status = rental.status
        rental.status = new_status
        rental.save()
        # سجل Log وتاريخ حالة
        SelfDriveRentalLog.objects.create(rental=rental, action='status_change', user=request.user, details=f'Status changed from {old_status} to {new_status}')
        SelfDriveRentalStatusHistory.objects.create(rental=rental, old_status=old_status, new_status=new_status, changed_by=request.user)
        return Response({'status': f'Status changed to {new_status}.'})

    @action(detail=True, methods=['post'])
    def add_manual_charge(self, request, pk=None):
        rental = self.get_object()
        if not hasattr(rental, 'breakdown'):
            return Response({'error_code': 'NO_BREAKDOWN', 'error_message': 'لا يوجد breakdown لهذه الرحلة.'}, status=400)
        amount = request.data.get('amount')
        if amount is None:
            return Response({'error_code': 'AMOUNT_REQUIRED', 'error_message': 'يجب تحديد قيمة المبلغ.'}, status=400)
        try:
            amount = float(amount)
        except ValueError:
            return Response({'error_code': 'AMOUNT_INVALID', 'error_message': 'قيمة المبلغ يجب أن تكون رقم.'}, status=400)
        rental.breakdown.base_cost += amount
        rental.breakdown.final_cost += amount
        rental.breakdown.save()
        if hasattr(rental, 'payment'):
            rental.payment.rental_total_amount = rental.breakdown.final_cost
            rental.payment.save()
        return Response({'status': 'Manual charge applied.', 'final_cost': rental.breakdown.final_cost})

    @action(detail=True, methods=['post'])
    def recalculate_invoice(self, request, pk=None):
        rental = self.get_object()
        payment = calculate_selfdrive_payment(rental)
        return Response({
            'breakdown': SelfDriveRentalBreakdownSerializer(rental.breakdown).data if hasattr(rental, 'breakdown') else None,
            'payment': SelfDrivePaymentSerializer(payment).data if payment else None
        })

    @action(detail=True, methods=['post'], url_path='deposit_payment')
    def deposit_payment(self, request, pk=None):
        rental = self.get_object()
        if check_deposit_expiry(rental):
            return Response({'error_code': 'DEPOSIT_EXPIRED', 'error_message': 'انتهت مهلة دفع الديبوزيت، تم إلغاء الحجز.'}, status=400)
        payment = rental.payment
        # --- منع دفع الديبوزيت مرتين ---
        if payment and payment.deposit_paid_status == 'Paid':
            return Response({'error_code': 'ALREADY_PAID', 'error_message': 'تم دفع العربون بالفعل ولا يمكن دفعه مرة أخرى.'}, status=400)
        payment_type = request.data.get('type', 'deposit')  # deposit/remaining/excess
        now = timezone.now()
        contract = rental.contract

        # --- الدفع بالكارت المحفوظ عبر Paymob ---
        payment_method = request.data.get('payment_method')
        saved_card_id = request.data.get('saved_card_id')
        amount_cents = request.data.get('amount_cents')
        if payment_method == 'saved_card' and saved_card_id and amount_cents and payment_type == 'deposit':
            try:
                # --- VALIDATION ---
                from payments.models import SavedCard
                from payments.services.payment_gateway import pay_with_saved_card_gateway
                
                # 0. تأكد أن المالك أكد الحجز أولاً
                if rental.status != 'DepositRequired':
                    return Response({'error_code': 'OWNER_CONFIRMATION_REQUIRED', 'error_message': 'يجب أن يؤكد مالك السيارة الحجز أولاً قبل دفع العربون.'}, status=400)
                
                # 1. تأكد أن المستخدم هو المستأجر
                if rental.renter != request.user:
                    return Response({'error_code': 'NOT_RENTER', 'error_message': 'يجب أن تكون المستأجر في هذا الحجز.'}, status=403)
                # 2. تأكد من وجود الكارت وأنه ملك للمستخدم
                try:
                    card = SavedCard.objects.get(id=saved_card_id, user=request.user)
                except SavedCard.DoesNotExist:
                    return Response({'error_code': 'CARD_NOT_FOUND', 'error_message': 'الكارت غير موجود أو لا يخصك.'}, status=404)
                # 3. تأكد من وجود بيانات الدفع
                if not payment or not hasattr(payment, 'deposit_amount'):
                    return Response({'error_code': 'PAYMENT_NOT_FOUND', 'error_message': 'لا يوجد بيانات دفع مرتبطة بهذا الحجز.'}, status=400)
                # 4. تأكد أن مبلغ الديبوزيت هو المطلوب بالضبط
                required_cents = int(round(float(payment.deposit_amount) * 100))
                if int(amount_cents) != required_cents:
                    return Response({'error_code': 'INVALID_AMOUNT', 'error_message': f'المبلغ المطلوب للعربون هو {required_cents} قرش.'}, status=400)
                # --- END VALIDATION ---
                result = pay_with_saved_card_gateway(int(amount_cents), request.user, card.token)
                if not result['success']:
                    return Response({'error_code': 'PAYMENT_FAILED', 'error_message': result['message'], 'details': result.get('charge_response')}, status=400)
                payment.deposit_paid_status = 'Paid'
                payment.deposit_paid_at = now
                payment.deposit_transaction_id = result['transaction_id']
                payment.payment_method = 'visa'
                payment.save()
                
                # Change rental status from DepositRequired to Confirmed
                old_status = rental.status
                rental.status = 'Confirmed'
                rental.save()
                
                # Log the status change
                from .models import SelfDriveRentalStatusHistory
                SelfDriveRentalStatusHistory.objects.create(rental=rental, old_status=old_status, new_status='Confirmed', changed_by=request.user)
                
                # Send payment notification to owner with detailed handover data
                try:
                    from notifications.models import Notification
                    
                    # Get renter and owner names
                    renter_name = f"{rental.renter.first_name} {rental.renter.last_name}".strip() or rental.renter.email
                    owner_name = f"{rental.car.owner.first_name} {rental.car.owner.last_name}".strip() or rental.car.owner.email
                    car_name = f"{rental.car.brand} {rental.car.model}"
                    
                    # Detailed notification data for owner pickup handover
                    notification_data = {
                        "rentalId": rental.id,
                        "renterId": rental.renter.id,
                        "carId": rental.car.id,
                        "status": rental.status,
                        "startDate": rental.start_date.isoformat(),
                        "endDate": rental.end_date.isoformat(),
                        "pickupAddress": rental.pickup_address,
                        "dropoffAddress": rental.dropoff_address,
                        "renterName": renter_name,
                        "carName": car_name,
                        "depositAmount": float(payment.deposit_amount),
                        "transactionId": result['transaction_id'],
                        "paymentMethod": "saved_card",
                        "cardLast4": card.card_last_four_digits if hasattr(card, 'card_last_four_digits') else "****",
                        "cardBrand": card.card_brand if hasattr(card, 'card_brand') else "Card",
                        
                        # Complete car details
                        "carDetails": {
                            "plateNumber": rental.car.plate_number,
                            "brand": rental.car.brand,
                            "model": rental.car.model,
                            "year": rental.car.year,
                            "color": rental.car.color,
                            "carType": rental.car.car_type,
                            "carCategory": rental.car.car_category,
                            "transmissionType": rental.car.transmission_type,
                            "fuelType": rental.car.fuel_type,
                            "seatingCapacity": rental.car.seating_capacity,
                            "currentOdometer": rental.car.current_odometer_reading,
                            "avgRating": float(rental.car.avg_rating),
                            "totalReviews": rental.car.total_reviews,
                            "dailyPrice": float(rental.car.rental_options.daily_rental_price) if hasattr(rental.car, 'rental_options') else 0,
                            "images": self._get_car_images(rental.car, request)
                        },
                        
                        # Renter details
                        "renterDetails": {
                            "name": renter_name,
                            "phone": rental.renter.phone_number,
                            "email": rental.renter.email,
                            "rating": float(rental.renter.avg_rating) if hasattr(rental.renter, 'avg_rating') else 0,
                            "reportsCount": rental.renter.reports_count if hasattr(rental.renter, 'reports_count') else 0
                        },
                        
                        # Payment details for owner pickup handover
                        "remainingAmount": float(payment.remaining_amount),
                        "totalAmount": float(payment.rental_total_amount),
                        "rentalPaymentMethod": getattr(rental, 'payment_method', 'visa'),
                        "cashCollectionRequired": getattr(rental, 'payment_method', 'visa') == 'cash',
                        "cashAmountToCollect": float(payment.remaining_amount) if getattr(rental, 'payment_method', 'visa') == 'cash' else 0,
                        "automaticPayment": getattr(rental, 'payment_method', 'visa') in ['visa', 'wallet'],
                        "selectedCardInfo": {
                            "cardBrand": rental.selected_card.card_brand if rental.selected_card else None,
                            "cardLast4": rental.selected_card.card_last_four_digits if rental.selected_card else None,
                            "cardId": rental.selected_card.id if rental.selected_card else None
                        } if rental.selected_card else None,
                        
                        # Trip details
                        "plannedKm": float(rental.planned_km) if hasattr(rental, 'planned_km') else 0,
                        "dailyPrice": float(rental.daily_price) if hasattr(rental, 'daily_price') else 0,
                        "totalDays": (rental.end_date.date() - rental.start_date.date()).days + 1,
                        "rentalType": "self_drive",
                        
                        # Owner earnings info
                        "ownerEarnings": float(payment.owner_earnings) if hasattr(payment, 'owner_earnings') else 0,
                        "platformFee": float(payment.platform_fee) if hasattr(payment, 'platform_fee') else 0,
                        "commissionRate": 0.2,  # Default commission rate
                        
                        # Handover instructions
                        "handoverInstructions": [
                            "Verify renter identity",
                            "Check car condition before handover",
                            "Confirm pickup location",
                            "Collect cash payment" if getattr(rental, 'payment_method', 'visa') == 'cash' else "Payment will be processed automatically",
                            "Start trip tracking"
                        ],
                        "nextAction": "owner_pickup_handover",
                        
                        # Owner pickup handover specific data
                        "handoverType": "cash_collection" if getattr(rental, 'payment_method', 'visa') == 'cash' else "automatic_payment",
                        "handoverMessage": f"Collect {float(payment.remaining_amount)} EGP in cash from renter" if getattr(rental, 'payment_method', 'visa') == 'cash' else "No cash collection needed - payment will be processed automatically",
                        "handoverStatus": "pending_cash_collection" if getattr(rental, 'payment_method', 'visa') == 'cash' else "automatic_payment_setup",
                        "handoverActions": [
                            "Confirm renter identity",
                            "Inspect car condition",
                            "Collect cash payment" if getattr(rental, 'payment_method', 'visa') == 'cash' else "Verify automatic payment setup",
                            "Start trip"
                        ],
                        "handoverNotes": [
                            f"Deposit paid: {float(payment.deposit_amount)} EGP",
                            f"Remaining amount: {float(payment.remaining_amount)} EGP",
                            f"Payment method: {getattr(rental, 'payment_method', 'visa').upper()}",
                            f"Trip duration: {(rental.end_date.date() - rental.start_date.date()).days + 1} days",
                            f"Pickup location: {rental.pickup_address}",
                            f"Dropoff location: {rental.dropoff_address}"
                        ],
                        "handoverWarnings": [
                            "Ensure you have proper change for cash payment" if getattr(rental, 'payment_method', 'visa') == 'cash' else "Payment will be charged automatically at trip end",
                            "Verify renter's driving license",
                            "Check car fuel level before handover",
                            "Document any existing damage"
                        ],
                        "handoverChecklist": [
                            "✅ Renter ID verification",
                            "✅ Driving license check",
                            "✅ Car condition inspection",
                            "✅ Fuel level confirmation",
                            "✅ Damage documentation",
                            "✅ Cash collection" if getattr(rental, 'payment_method', 'visa') == 'cash' else "✅ Payment method verification",
                            "✅ Trip start confirmation"
                        ],
                        "handoverSummary": {
                            "totalEarnings": float(payment.owner_earnings) if hasattr(payment, 'owner_earnings') else 0,
                            "platformCommission": float(payment.platform_fee) if hasattr(payment, 'platform_fee') else 0,
                            "commissionPercentage": 20.0,
                            "cashToCollect": float(payment.remaining_amount) if getattr(rental, 'payment_method', 'visa') == 'cash' else 0,
                            "automaticPayment": getattr(rental, 'payment_method', 'visa') in ['visa', 'wallet'],
                            "tripDuration": f"{(rental.end_date.date() - rental.start_date.date()).days + 1} days",
                            "pickupTime": rental.start_date.strftime("%Y-%m-%d %H:%M"),
                            "dropoffTime": rental.end_date.strftime("%Y-%m-%d %H:%M")
                        }
                    }
                    
                    # Notification for owner - more interactive and action-oriented
                    owner_notification = Notification.objects.create(
                        sender=rental.renter,
                        receiver=rental.car.owner,
                        title="💰 Deposit Payment Received - Action Required",
                        message=f"Great news! {renter_name} has successfully paid the deposit of {payment.deposit_amount} EGP for your {car_name}. Your rental is now confirmed and ready for pickup. Please proceed with the handover process.",
                        notification_type="PAYMENT",
                        priority="HIGH",
                        data=notification_data,
                        navigation_id="DEP_OWNER",
                        is_read=False
                    )
                    
                    # Notification for renter - confirmation and next steps
                    renter_notification_data = {
                        "rentalId": rental.id,
                        "carName": car_name,
                        "depositAmount": str(payment.deposit_amount),
                        "totalAmount": float(payment.rental_total_amount),
                        "remainingAmount": float(payment.remaining_amount),
                        "pickupDate": rental.start_date.strftime("%Y-%m-%d %H:%M"),
                        "pickupLocation": rental.pickup_address,
                        "nextStep": "Ready for pickup",
                        "status": "confirmed"
                    }
                    
                    renter_notification = Notification.objects.create(
                        sender=rental.car.owner,
                        receiver=rental.renter,
                        title="✅ Deposit Payment Confirmed",
                        message=f"Thank you for paying the deposit of {payment.deposit_amount} EGP for {car_name} using your saved card. Your rental is now confirmed and ready for pickup on {rental.start_date.strftime('%Y-%m-%d at %H:%M')}. Please contact the owner to arrange the handover.",
                        notification_type="PAYMENT",
                        priority="HIGH",
                        data=renter_notification_data,
                        navigation_id="RENTAL_CONFIRMED",
                        is_read=False
                    )
                    print(f"✅ Self-drive deposit notifications created successfully: Owner={owner_notification.id}, Renter={renter_notification.id}")
                except Exception as e:
                    print(f"❌ Error sending self-drive deposit notification: {str(e)}")
                    import traceback
                    traceback.print_exc()
                
                from .serializers import SelfDrivePaymentSerializer
                return Response({
                    'status': 'deposit payment processed successfully.',
                    'transaction_id': result['transaction_id'],
                    'payment': SelfDrivePaymentSerializer(payment).data,
                    'paymob_details': result,
                    'old_status': old_status,
                    'new_status': rental.status
                })
            except Exception as e:
                return Response({'error_code': 'PAYMENT_ERROR', 'error_message': str(e)}, status=500)

        # Default response for other payment methods or missing parameters
        return Response({
            'error_code': 'INVALID_PAYMENT_METHOD', 
            'error_message': 'طريقة الدفع غير صحيحة أو بيانات مفقودة. يجب استخدام saved_card مع saved_card_id و amount_cents.',
            'required_parameters': {
                'payment_method': 'saved_card',
                'saved_card_id': 'integer',
                'amount_cents': 'integer',
                'type': 'deposit'
            }
        }, status=400)

    @action(detail=True, methods=['post'])
    def receive_live_location(self, request, pk=None):
        rental = self.get_object()
        latitude = request.data.get('latitude')
        longitude = request.data.get('longitude')
        timestamp = request.data.get('timestamp', None)
        if not latitude or not longitude:
            return Response({'error_code': 'LOCATION_REQUIRED', 'error_message': 'latitude و longitude مطلوبين.'}, status=400)
        location = SelfDriveLiveLocation.objects.create(
            rental=rental,
            latitude=latitude,
            longitude=longitude,
            timestamp=timestamp if timestamp else timezone.now()
        )
        return Response({'status': 'Location received.', 'location_id': location.id})

    @action(detail=True, methods=['post'])
    def confirm_by_owner(self, request, pk=None):
        rental = self.get_object()
        payment = rental.payment
        if rental.status != 'PendingOwnerConfirmation':
            return Response({'error_code': 'INVALID_STATUS', 'error_message': 'لا يمكن تأكيد الحجز إلا إذا كان في حالة انتظار تأكيد المالك.'}, status=400)
        if rental.car.owner != request.user:
            return Response({'error_code': 'NOT_OWNER', 'error_message': 'فقط مالك السيارة يمكنه تأكيد الحجز.'}, status=403)
        # تحقق من رصيد محفظة المالك
        owner_wallet = rental.car.owner.wallet
        if owner_wallet.balance < -1000:
            return Response({'error_code': 'WALLET_LIMIT', 'error_message': 'لا يمكنك تأكيد الحجز. رصيد محفظتك أقل من -1000. يرجى شحن المحفظة أولاً.'}, status=403)
        old_status = rental.status
        rental.status = 'DepositRequired'
        rental.save()
        payment.deposit_due_at = timezone.now() + timedelta(days=1)
        payment.save()
        SelfDriveRentalLog.objects.create(rental=rental, action='owner_confirm', user=request.user, details='Owner confirmed the rental.')
        SelfDriveRentalStatusHistory.objects.create(rental=rental, old_status=old_status, new_status='DepositRequired', changed_by=request.user)
        
        # Send booking accepted notification to renter
        try:
            print(f"DEBUG: About to send booking accepted notification for rental {rental.id}")
            from notifications.models import Notification
            from payments.models import SavedCard
            
            # Get car details
            car_name = f"{rental.car.brand} {rental.car.model}"
            deposit_amount = float(payment.deposit_amount)
            
            # Get renter's saved cards
            saved_cards = SavedCard.objects.filter(user=rental.renter)
            payment_methods = []
            
            # Add saved cards to payment methods
            for card in saved_cards:
                payment_methods.append({
                    "type": "card",
                    "id": card.id,
                    "last4": card.card_last_four_digits,
                    "brand": card.card_brand,
                    "token": card.token
                })
            
            # Only include saved cards, no wallet or cash
            
            # Create notification data
            notification_data = {
                "carId": rental.car.id,
                "depositAmount": str(deposit_amount),
                "status": "accepted",
                "nextStep": "Pay deposit",
                "paymentMethods": payment_methods,
                "rentalId": rental.id,
                "carName": car_name,
                "totalAmount": float(payment.rental_total_amount),
                "remainingAmount": float(payment.remaining_amount)
            }
            
            print(f"DEBUG: Notification data: {notification_data}")
            
            # Create notification
            notification = Notification.objects.create(
                sender=rental.car.owner,  # Owner is the sender
                receiver=rental.renter,   # Renter is the receiver
                title="Booking Request Accepted",
                message=f"Your booking request for {car_name} has been accepted by the owner. You need to pay the deposit amount of {deposit_amount} EGP within 24 hours.",
                notification_type="RENTAL",
                priority="HIGH",
                data=notification_data,
                navigation_id="ACC_RENTER",
                is_read=False
            )
            
            print(f"DEBUG: Notification created successfully: {notification.id}")
        except Exception as e:
            print(f"Error sending booking accepted notification: {str(e)}")
            import traceback
            traceback.print_exc()
        
        return Response({'status': 'تم تأكيد الحجز من المالك. يجب دفع العربون خلال 24 ساعة.'})

    @action(detail=True, methods=['post'])
    def deposit_paid(self, request, pk=None):
        rental = self.get_object()
        payment = rental.payment
        
        # Check if owner has confirmed the rental first
        if rental.status != 'DepositRequired':
            return Response({'error_code': 'OWNER_CONFIRMATION_REQUIRED', 'error_message': 'يجب أن يؤكد مالك السيارة الحجز أولاً قبل دفع العربون.'}, status=400)
        
        if payment.deposit_paid_status == 'Paid':
            return Response({'error_code': 'ALREADY_PAID', 'error_message': 'تم دفع العربون بالفعل.'}, status=400)
        
        # Update payment status
        payment.deposit_paid_status = 'Paid'
        payment.deposit_paid_at = timezone.now()
        payment.save()
        
        # Change rental status from DepositRequired to Confirmed
        old_status = rental.status
        rental.status = 'Confirmed'
        rental.save()
        
        # توليد العقد PDF بعد دفع العربون
        contract = rental.contract
        contract_pdf_bytes = generate_contract_pdf(rental)
        contract.contract_pdf.save(f'contract_rental_{rental.id}.pdf', ContentFile(contract_pdf_bytes))
        contract.save()
        
        # Log the changes
        SelfDriveRentalLog.objects.create(rental=rental, action='deposit_paid', user=request.user, details='Renter paid the deposit. Contract generated.')
        from .models import SelfDriveRentalStatusHistory
        SelfDriveRentalStatusHistory.objects.create(rental=rental, old_status=old_status, new_status='Confirmed', changed_by=request.user)
        
        return Response({
            'status': 'تم دفع العربون وتم توليد العقد.',
            'old_status': old_status,
            'new_status': rental.status
        })

    @action(detail=True, methods=['post'])
    def owner_pickup_handover(self, request, pk=None):
        rental = self.get_object()
        contract = rental.contract
        payment = rental.payment
        # تحقق من دفع العربون
        if payment.deposit_paid_status != 'Paid':
            return Response({'error_code': 'DEPOSIT_REQUIRED', 'error_message': 'يجب دفع العربون قبل التسليم.'}, status=400)
        # تحقق من عدم تكرار التسليم
        if contract.owner_pickup_done:
            return Response({'error_code': 'ALREADY_DONE', 'error_message': 'تم تسليم السيارة من المالك بالفعل.'}, status=400)
        # تحقق من رفع صورة العقد
        contract_image = request.FILES.get('contract_image')
        if not contract_image:
            return Response({'error_code': 'CONTRACT_IMAGE_REQUIRED', 'error_message': 'صورة العقد الموقعة من المالك مطلوبة (contract_image).'}, status=400)
        contract.owner_contract_image.save(f'owner_contract_pickup_{rental.id}.jpg', contract_image)
        # تحقق من توقيع المالك
        if not contract.owner_signed:
            contract.owner_signed = True
            contract.owner_signed_at = timezone.now()
        # تحقق من استلام الكاش إذا كان الدفع كاش
        confirm_remaining_cash = request.data.get('confirm_remaining_cash')
        if payment.payment_method == 'cash':
            if str(confirm_remaining_cash).lower() == 'true':
                if payment.remaining_paid_status == 'Confirmed':
                    return Response({'error_code': 'REMAINING_ALREADY_CONFIRMED', 'error_message': 'تم تأكيد استلام باقي المبلغ كاش بالفعل.'}, status=400)
                payment.remaining_paid_status = 'Confirmed'
                payment.remaining_paid_at = timezone.now()
                payment.save()
                SelfDriveRentalLog.objects.create(rental=rental, action='payment', user=request.user, details='Confirmed receiving remaining cash at pickup.')
            else:
                return Response({'error_code': 'CASH_CONFIRM_REQUIRED', 'error_message': 'يجب على المالك تأكيد استلام باقي المبلغ كاش عبر confirm_remaining_cash=true.'}, status=400)
        else:
            if confirm_remaining_cash is not None:
                return Response({'error_code': 'CASH_NOT_ALLOWED', 'error_message': 'الدفع إلكتروني ولا يمكن تأكيد استلام كاش.'}, status=400)
        # نفذ التسليم
        contract.owner_pickup_done = True
        contract.owner_pickup_done_at = timezone.now()
        contract.save()
        SelfDriveRentalLog.objects.create(rental=rental, action='owner_pickup_handover', user=request.user, details='Owner did pickup handover with contract image and signature.')
        
        # إرسال إشعار للرينتر أن المالك أكمل الهاند أوفر
        try:
            from notifications.models import Notification
            
            # Get names
            owner_name = f"{rental.car.owner.first_name} {rental.car.owner.last_name}".strip() or rental.car.owner.email
            car_name = f"{rental.car.brand} {rental.car.model}"
            
            # Detailed notification data for renter pickup handover
            notification_data = {
                "rentalId": rental.id,
                "ownerId": rental.car.owner.id,
                "carId": rental.car.id,
                "status": rental.status,
                "startDate": rental.start_date.isoformat(),
                "endDate": rental.end_date.isoformat(),
                "pickupAddress": rental.pickup_address,
                "dropoffAddress": rental.dropoff_address,
                "ownerName": owner_name,
                "carName": car_name,
                "carPlateNumber": rental.car.plate_number,
                "carBrand": rental.car.brand,
                "carModel": rental.car.model,
                "carYear": rental.car.year,
                "carColor": rental.car.color,
                "carType": rental.car.car_type,
                "carCategory": rental.car.car_category,
                "carTransmission": rental.car.transmission_type,
                "carFuelType": rental.car.fuel_type,
                "carSeatingCapacity": rental.car.seating_capacity,
                "carCurrentOdometer": rental.car.current_odometer_reading,
                
                # Payment details for renter pickup handover
                "depositAmount": float(payment.deposit_amount),
                "remainingAmount": float(payment.remaining_amount),
                "totalAmount": float(payment.rental_total_amount),
                "paymentMethod": payment.payment_method,
                "depositPaidStatus": payment.deposit_paid_status,
                "remainingPaidStatus": payment.remaining_paid_status,
                
                # Selected card info (if applicable)
                "selectedCardInfo": {
                    "cardBrand": rental.selected_card.card_brand if rental.selected_card else None,
                    "cardLast4": rental.selected_card.card_last_four_digits if rental.selected_card else None,
                    "cardId": rental.selected_card.id if rental.selected_card else None
                } if rental.selected_card else None,
                
                # Trip details
                "tripDuration": (rental.end_date.date() - rental.start_date.date()).days + 1,
                "rentalType": "self_drive",
                
                # Handover instructions for renter
                "handoverInstructions": [
                    "Verify owner identity",
                    "Check car condition before pickup",
                    "Take photos of car and odometer",
                    "Sign contract if not signed",
                    "Pay remaining amount" if payment.payment_method == 'cash' else "Payment will be processed automatically",
                    "Start trip tracking"
                ],
                "nextAction": "renter_pickup_handover",
                
                # Renter pickup handover specific data
                "handoverType": "cash_payment" if payment.payment_method == 'cash' else "automatic_payment",
                "handoverMessage": f"Pay {float(payment.remaining_amount)} EGP in cash to owner" if payment.payment_method == 'cash' else "Payment will be processed automatically from your selected card",
                "handoverStatus": "pending_cash_payment" if payment.payment_method == 'cash' else "automatic_payment_setup",
                "handoverActions": [
                    "Verify owner identity",
                    "Inspect car condition",
                    "Take car and odometer photos",
                    "Pay cash amount" if payment.payment_method == 'cash' else "Confirm automatic payment",
                    "Start trip"
                ],
                "handoverNotes": [
                    f"Deposit paid: {float(payment.deposit_amount)} EGP",
                    f"Remaining amount: {float(payment.remaining_amount)} EGP",
                    f"Payment method: {payment.payment_method.upper()}",
                    f"Trip duration: {(rental.end_date.date() - rental.start_date.date()).days + 1} days",
                    f"Pickup location: {rental.pickup_address}",
                    f"Dropoff location: {rental.dropoff_address}",
                    f"Car: {car_name} ({rental.car.plate_number})",
                    f"Owner: {owner_name}"
                ],
                "event": "owner_pickup_completed"
            }
            
            # Send notification to renter
            Notification.objects.create(
                receiver=rental.renter,
                title="🚗 Ready to Start Your Trip!",
                message=f"Hey {rental.renter.first_name}! The owner {owner_name} is ready to hand over your car {car_name} 🎯\n\n✅ You can now complete the handover and start your amazing trip!\n💡 Remember: Check the car condition and sign the contract before driving",
                notification_type="RENTAL",
                priority="HIGH",
                data=notification_data,
                navigation_id="REN_PICKUP_HND"
            )
            print(f"✅ Owner pickup completion notification sent to renter successfully")
            
            # Send notification to owner confirming handover completion
            owner_notification_data = {
                "rentalId": rental.id,
                "renterId": rental.renter.id,
                "carId": rental.car.id,
                "status": rental.status,
                "renterName": f"{rental.renter.first_name} {rental.renter.last_name}".strip() or rental.renter.email,
                "carName": car_name,
                "handoverCompleted": True,
                "handoverCompletedAt": contract.owner_pickup_done_at.isoformat(),
                "nextStep": "wait_for_renter_handover",
                "message": "تم تسليم السيارة بنجاح. انتظر المستأجر لإكمال الهاند أوفر.",
                "event": "owner_pickup_completed"
            }
            
            Notification.objects.create(
                receiver=rental.car.owner,
                title="✅ Car Handover Completed Successfully!",
                message=f"Perfect! You've successfully handed over {car_name} to {rental.renter.first_name} 🎯\n\n⏰ Waiting for renter to complete final handover steps\n💡 Tip: Make sure to explain all car features and safety instructions",
                notification_type="RENTAL",
                priority="MEDIUM",
                data=owner_notification_data,
                navigation_id="OWN_PICKUP_COMPLETE"
            )
            print(f"✅ Owner pickup completion confirmation notification sent to owner successfully")
            
        except Exception as e:
            print(f"❌ Error sending owner pickup completion notifications: {e}")
            import traceback
            traceback.print_exc()
        
        return Response({
            'status': 'تم تسليم السيارة من المالك.',
            'owner_signed': contract.owner_signed,
            'contract_image': contract.owner_contract_image.url if contract.owner_contract_image else None,
            'remaining_paid_status': payment.remaining_paid_status
        })

    @action(detail=True, methods=['post'])
    def renter_pickup_handover(self, request, pk=None):
        rental = self.get_object()
        contract = rental.contract
        payment = rental.payment
        # يجب أن يكون المالك عمل هاند أوفر
        if not contract.owner_pickup_done:
            return Response({'error_code': 'OWNER_PICKUP_REQUIRED', 'error_message': 'يجب أن يقوم المالك بتسليم السيارة أولاً.'}, status=400)
        if contract.renter_pickup_done:
            return Response({'error_code': 'ALREADY_DONE', 'error_message': 'تم استلام السيارة من المستأجر بالفعل.'}, status=400)
        # تحقق من رفع صورة السيارة وصورة العداد
        car_image = request.FILES.get('car_image')
        odometer_image = request.FILES.get('odometer_image')
        odometer_value = request.data.get('odometer_value')
        if not car_image:
            return Response({'error_code': 'CAR_IMAGE_REQUIRED', 'error_message': 'صورة العربية مطلوبة.'}, status=400)
        if not odometer_image or not odometer_value:
            return Response({'error_code': 'ODOMETER_START_REQUIRED', 'error_message': 'صورة وقراءة عداد البداية مطلوبة.'}, status=400)
        from .models import SelfDriveCarImage, SelfDriveOdometerImage

        # --- تعديل التسمية ---
        car_identifier = getattr(rental.car, 'plate_number', None) or getattr(rental.car, 'model', 'car')
        car_identifier = str(car_identifier).replace(' ', '_')
        rental_type = 'pickup'
        # car image
        car_image.name = f"{car_identifier}_{rental_type}_car_{rental.id}.png"
        SelfDriveCarImage.objects.create(rental=rental, image=car_image, type=rental_type, uploaded_by='renter')
        # odometer image
        odometer_image.name = f"{car_identifier}_{rental_type}_odometer_{rental.id}.png"
        SelfDriveOdometerImage.objects.create(rental=rental, image=odometer_image, value=odometer_value, type='start')

        #from .models import SelfDriveCarImage
        #SelfDriveCarImage.objects.create(rental=rental, image=car_image, type='pickup', uploaded_by='renter')
        #from .models import SelfDriveOdometerImage
        #SelfDriveOdometerImage.objects.create(rental=rental, image=odometer_image, value=odometer_value, type='start')
        # تحقق من توقيع المستأجر
        if not contract.renter_signed:
            contract.renter_signed = True
            contract.renter_signed_at = timezone.now()
        # تحقق من دفع باقي المبلغ لو إلكتروني
        confirm_remaining_cash = request.data.get('confirm_remaining_cash')
        if payment.payment_method in ['visa', 'wallet']:
            if confirm_remaining_cash is not None:
                return Response({'error_code': 'CASH_NOT_ALLOWED', 'error_message': 'الدفع إلكتروني ولا يمكن تأكيد استلام كاش.'}, status=400)
        if payment.payment_method == 'visa':
            # دفع فعلي بالكارت المحفوظ المختار
            selected_card = getattr(rental, 'selected_card', None)
            if not selected_card:
                return Response({'error_code': 'NO_SELECTED_CARD', 'error_message': 'لم يتم اختيار كارت فيزا لهذا الحجز.'}, status=400)
            if selected_card.user != request.user:
                return Response({'error_code': 'CARD_NOT_OWNED', 'error_message': 'الكارت المختار لا يخصك.'}, status=403)
            from payments.services.payment_gateway import pay_with_saved_card_gateway
            amount_cents = int(round(float(payment.remaining_amount) * 100))
            result = pay_with_saved_card_gateway(amount_cents, request.user, selected_card.token)
            # سجل كل تفاصيل الدفع
            payment.remaining_paid_status = 'Paid' if result['success'] else 'Pending'
            payment.remaining_paid_at = timezone.now() if result['success'] else None
            payment.remaining_transaction_id = result['transaction_id']
            payment.save()
            from .models import SelfDriveRentalLog
            SelfDriveRentalLog.objects.create(
                rental=payment.rental,
                action='payment',
                user=request.user,
                details=f'Remaining payment: {result}'
            )
            if not result['success']:
                return Response({'error_code': 'PAYMENT_FAILED', 'error_message': result['message'], 'paymob_details': result}, status=400)
            paymob_details = result
        else:
            paymob_details = None
            if payment.payment_method == 'wallet':
                # ... الكود القديم لو محفظة ...
                pass
        # لو كاش لا يتم أي تحديث هنا
        # نفذ هاند أوفر المستأجر
        contract.renter_pickup_done = True
        contract.renter_pickup_done_at = timezone.now()
        contract.save()
        SelfDriveRentalLog.objects.create(rental=rental, action='renter_pickup_handover', user=request.user, details='Renter did pickup handover with car image and odometer.')
        
        # بدء الرحلة تلقائياً بعد اكتمال الهاند أوفر
        trip_started = False
        trip_start_error = None
        
        try:
            # نفس التشيكس الموجودة في start_trip
            if not (contract.renter_pickup_done and contract.owner_pickup_done and contract.renter_signed and contract.owner_signed):
                trip_start_error = 'يجب إتمام التسليم والتوقيع من الطرفين قبل بدء الرحلة.'
            elif payment.deposit_paid_status != 'Paid':
                trip_start_error = 'يجب دفع العربون قبل بدء الرحلة.'
            elif payment.payment_method in ['visa', 'wallet'] and payment.remaining_paid_status != 'Paid':
                trip_start_error = 'يجب دفع باقي المبلغ إلكترونياً قبل بدء الرحلة.'
            elif payment.payment_method == 'cash' and payment.remaining_paid_status != 'Confirmed':
                trip_start_error = 'يجب تأكيد استلام باقي المبلغ كاش قبل بدء الرحلة.'
            elif rental.status == 'Ongoing':
                trip_start_error = 'تم بدء الرحلة بالفعل.'
            else:
                # بدء الرحلة
                old_status = rental.status
                rental.status = 'Ongoing'
                rental.save()
                SelfDriveRentalLog.objects.create(rental=rental, action='trip_started', user=request.user, details='Trip started automatically after renter pickup handover.')
                from .models import SelfDriveRentalStatusHistory
                SelfDriveRentalStatusHistory.objects.create(rental=rental, old_status=old_status, new_status='Ongoing', changed_by=request.user)
                trip_started = True
                print(f"✅ Trip started automatically for rental #{rental.id}")
                
        except Exception as e:
            trip_start_error = f'خطأ في بدء الرحلة: {str(e)}'
            print(f"❌ Error starting trip automatically: {e}")
            import traceback
            traceback.print_exc()
        
        # إرسال إشعارات محدثة
        try:
            from notifications.models import Notification
            
            # Get names
            renter_name = f"{rental.renter.first_name} {rental.renter.last_name}".strip() or rental.renter.email
            owner_name = f"{rental.car.owner.first_name} {rental.car.owner.last_name}".strip() or rental.car.owner.email
            car_name = f"{rental.car.brand} {rental.car.model}"
            
            # Detailed notification data for owner with complete car details
            owner_notification_data = {
                "rentalId": rental.id,
                "renterId": rental.renter.id,
                "carId": rental.car.id,
                "status": rental.status,
                "startDate": rental.start_date.isoformat(),
                "endDate": rental.end_date.isoformat(),
                "pickupAddress": rental.pickup_address,
                "dropoffAddress": rental.dropoff_address,
                "renterName": renter_name,
                "carName": car_name,
                
                # Complete car details
                "carDetails": {
                    "plateNumber": rental.car.plate_number,
                    "brand": rental.car.brand,
                    "model": rental.car.model,
                    "year": rental.car.year,
                    "color": rental.car.color,
                    "carType": rental.car.car_type,
                    "carCategory": rental.car.car_category,
                    "transmissionType": rental.car.transmission_type,
                    "fuelType": rental.car.fuel_type,
                    "seatingCapacity": rental.car.seating_capacity,
                    "currentOdometer": rental.car.current_odometer_reading,
                    "avgRating": float(rental.car.avg_rating),
                    "totalReviews": rental.car.total_reviews,
                    "dailyPrice": float(rental.car.rental_options.daily_rental_price) if hasattr(rental.car, 'rental_options') else 0,
                    "images": self._get_car_images(rental.car, request)
                },
                
                # Renter details
                "renterDetails": {
                    "name": renter_name,
                                                "phone": rental.renter.phone_number,
                    "email": rental.renter.email,
                    "rating": float(rental.renter.avg_rating) if hasattr(rental.renter, 'avg_rating') else 0,
                    "reportsCount": rental.renter.reports_count if hasattr(rental.renter, 'reports_count') else 0
                },
                
                # Payment details
                "paymentDetails": {
                    "depositAmount": float(payment.deposit_amount),
                    "remainingAmount": float(payment.remaining_amount),
                    "totalAmount": float(payment.rental_total_amount),
                    "paymentMethod": payment.payment_method,
                    "depositPaidStatus": payment.deposit_paid_status,
                    "remainingPaidStatus": payment.remaining_paid_status,
                    "remainingPaidAt": payment.remaining_paid_at.isoformat() if payment.remaining_paid_at else None,
                    "remainingTransactionId": payment.remaining_transaction_id,
                    "selectedCardInfo": {
                        "cardBrand": rental.selected_card.card_brand if rental.selected_card else None,
                        "cardLast4": rental.selected_card.card_last_four_digits if rental.selected_card else None,
                        "cardId": rental.selected_card.id if rental.selected_card else None
                    } if rental.selected_card else None
                },
                
                # Trip details
                "tripDetails": {
                    "duration": (rental.end_date.date() - rental.start_date.date()).days + 1,
                    "rentalType": "self_drive",
                    "tripStarted": trip_started,
                    "tripStartError": trip_start_error
                },
                
                # Handover details
                "handoverDetails": {
                    "ownerHandoverCompleted": contract.owner_pickup_done,
                    "ownerHandoverTime": contract.owner_pickup_done_at.isoformat() if contract.owner_pickup_done_at else None,
                    "renterHandoverCompleted": contract.renter_pickup_done,
                    "renterHandoverTime": contract.renter_pickup_done_at.isoformat() if contract.renter_pickup_done_at else None,
                    "contractSigned": contract.owner_signed and contract.renter_signed
                }
            }
            
            # Handover completion details
            owner_notification_data.update({
                "handoverCompleted": True,
                "handoverCompletedAt": contract.renter_pickup_done_at.isoformat(),
                "carImageUploaded": True,
                "odometerImageUploaded": True,
                "odometerValue": odometer_value,
                
                # Trip status
                "tripStarted": trip_started,
                "tripStartError": trip_start_error,
                
                # Next steps for owner
                "nextAction": "trip_ongoing" if trip_started else "trip_start_failed",
                "handoverMessage": f"Renter {renter_name} completed car pickup for {car_name}. Trip {'started successfully!' if trip_started else 'failed to start: ' + trip_start_error}",
                "handoverStatus": "completed",
                "handoverNotes": [
                    f"Deposit paid: {float(payment.deposit_amount)} EGP",
                    f"Remaining amount: {float(payment.remaining_amount)} EGP",
                    f"Payment method: {payment.payment_method.upper()}",
                    f"Payment status: {payment.remaining_paid_status}",
                    f"Trip duration: {(rental.end_date.date() - rental.start_date.date()).days + 1} days",
                    f"Pickup location: {rental.pickup_address}",
                    f"Dropoff location: {rental.dropoff_address}",
                    f"Car: {car_name} ({rental.car.plate_number})",
                    f"Renter: {renter_name}",
                    f"Handover completed at: {contract.renter_pickup_done_at.strftime('%Y-%m-%d %H:%M')}",
                    f"Trip status: {'Started' if trip_started else 'Failed to start'}"
                ],
                "event": "renter_pickup_completed"
            })
            
            # Send notification to owner
            if trip_started:
                owner_title = "🚀 Trip Started Successfully!"
                owner_message = f"Congratulations! Renter {renter_name} has completed car pickup for {car_name} and the trip has started successfully! 🎉\n\n📱 You can now track the trip in real-time\n💡 Tip: Make sure you have the renter's phone number for emergency contact\n\n🚗 Car Details:\n• {car_name} ({rental.car.plate_number})\n• {rental.car.year} • {rental.car.color} • {rental.car.transmission_type}\n• Daily Price: {float(rental.car.rental_options.daily_rental_price) if hasattr(rental.car, 'rental_options') else 0} EGP"
            else:
                owner_title = "⚠️ Renter Completed Pickup"
                owner_message = f"Renter {renter_name} has completed car pickup for {car_name} ✅\n\n❌ But trip didn't start: {trip_start_error}\n💡 Tip: Check that all requirements are met\n\n🚗 Car Details:\n• {car_name} ({rental.car.plate_number})\n• {rental.car.year} • {rental.car.color} • {rental.car.transmission_type}"
            
            Notification.objects.create(
                receiver=rental.car.owner,
                title=owner_title,
                message=owner_message,
                notification_type="RENTAL",
                priority="HIGH",
                data=owner_notification_data,
                navigation_id="OWN_ONGOING" if trip_started else "OWN_RENTER_COMPLETE"
            )
            print(f"✅ Renter pickup completion notification sent to owner successfully")
            
            # Send notification to renter confirming handover completion and trip start
            renter_notification_data = {
                "rentalId": rental.id,
                "ownerId": rental.car.owner.id,
                "carId": rental.car.id,
                "status": rental.status,
                "ownerName": owner_name,
                "carName": car_name,
                "handoverCompleted": True,
                "handoverCompletedAt": contract.renter_pickup_done_at.isoformat(),
                "paymentCompleted": payment.remaining_paid_status == 'Paid',
                "tripStarted": trip_started,
                "tripStartError": trip_start_error,
                "nextStep": "trip_ongoing" if trip_started else "trip_start_failed",
                "message": f"تم استلام السيارة بنجاح! الرحلة {'بدأت بنجاح!' if trip_started else 'لم تبدأ: ' + trip_start_error}",
                "event": "renter_pickup_completed"
            }
            
            if trip_started:
                renter_title = "🎉 Trip Started Successfully!"
                renter_message = f"Excellent! Car {car_name} has been successfully picked up and the trip has started! 🚗✨\n\n🎯 You can now enjoy your trip\n💡 Important tips:\n• Drive safely\n• Obey speed limits\n• Keep owner's phone number for emergencies\n• Make sure all doors are properly closed"
            else:
                renter_title = "✅ Car Pickup Completed"
                renter_message = f"Car {car_name} has been successfully picked up! ✅\n\n❌ But trip didn't start: {trip_start_error}\n💡 Tip: Check that all requirements are met or contact technical support"
            
            Notification.objects.create(
                receiver=rental.renter,
                title=renter_title,
                message=renter_message,
                notification_type="RENTAL",
                priority="MEDIUM",
                data=renter_notification_data,
                navigation_id="REN_ONGOING" if trip_started else "REN_PICKUP_COMPLETE"
            )
            print(f"✅ Renter pickup completion confirmation notification sent to renter successfully")
            
        except Exception as e:
            print(f"❌ Error sending renter pickup completion notifications: {e}")
            import traceback
            traceback.print_exc()
        
        return Response({
            'status': 'تم استلام السيارة من المستأجر.',
            'renter_signed': contract.renter_signed,
            'car_image': car_image.name,
            'odometer_image': odometer_image.name,
            'remaining_paid_status': payment.remaining_paid_status,
            'paymob_details': paymob_details,
            'trip_started': trip_started,
            'trip_start_error': trip_start_error
        })

    def _send_location_notification(self, rental, user, location_type):
        """Send location notifications to users"""
        try:
            from notifications.models import Notification
            
            if location_type == 'pickup':
                title = "📍 Arrived at Pickup Location!"
                message = f"Hello {user.first_name}! You've arrived at the car pickup location 🚗\n\n💡 Tip: Make sure the owner is present at the location before proceeding"
                navigation_id = "REN_PICKUP_LOCATION"
            elif location_type == 'dropoff':
                title = "🏁 Arrived at Dropoff Location!"
                message = f"Hello {user.first_name}! You've arrived at the car dropoff location 🎯\n\n💡 Tip: Make sure all doors are closed and engine is turned off"
                navigation_id = "REN_DROPOFF_LOCATION"
            
            notification_data = {
                "rentalId": rental.id,
                "locationType": location_type,
                "timestamp": timezone.now().isoformat(),
                "event": f"{location_type}_location_reached"
            }
            
            Notification.objects.create(  # type: ignore
                receiver=user,
                title=title,
                message=message,
                notification_type="LOCATION",
                priority="MEDIUM",
                data=notification_data,
                navigation_id=navigation_id
            )
            print(f"✅ Location notification sent to {user.first_name} for {location_type}")
            
        except Exception as e:
            print(f"❌ Error sending location notification: {e}")

    def _send_emergency_notification(self, rental, emergency_type, details=""):
        """Send emergency notifications"""
        try:
            from notifications.models import Notification
            
            emergency_messages = {
                'late_return': {
                    'title': "⚠️ Warning: Late Return",
                    'message': f"Warning! The trip has exceeded the scheduled return time ⏰\n\n💡 Tip: Contact the owner immediately to clarify the situation"
                },
                'payment_issue': {
                    'title': "💳 Payment Issue",
                    'message': f"A problem occurred while processing the payment 💳\n\n💡 Tip: Check your card details or contact technical support"
                },
                'car_issue': {
                    'title': "🚗 Car Issue",
                    'message': f"A car issue has been reported 🚗\n\n💡 Tip: Don't try to fix the problem yourself, contact the owner immediately"
                }
            }
            
            emergency_info = emergency_messages.get(emergency_type, {
                'title': "⚠️ Important Alert",
                'message': f"A problem occurred during the trip: {details}\n\n💡 Tip: Contact technical support immediately"
            })
            
            notification_data = {
                "rentalId": rental.id,
                "emergencyType": emergency_type,
                "details": details,
                "timestamp": timezone.now().isoformat(),
                "event": "emergency_alert"
            }
            
            # إرسال للمالك والمستأجر
            for user in [rental.car.owner, rental.renter]:
                Notification.objects.create(  # type: ignore
                    receiver=user,
                    title=emergency_info['title'],
                    message=emergency_info['message'],
                    notification_type="EMERGENCY",
                    priority="HIGH",
                    data=notification_data,
                    navigation_id="EMERGENCY_ALERT"
                )
            
            print(f"✅ Emergency notification sent for {emergency_type}")
            
        except Exception as e:
            print(f"❌ Error sending emergency notification: {e}")

    def _get_car_images(self, car, request):
        """Get car images from documents"""
        try:
            from documents.models import Document
            car_images = []
            car_documents = Document.objects.filter(car=car)  # type: ignore
            
            for doc in car_documents:
                if hasattr(doc, 'file') and doc.file and doc.file.name:
                    try:
                        if doc.file.storage.exists(doc.file.name) and not doc.file.name.endswith('/'):
                            if doc.file.url and not doc.file.url.endswith('/'):
                                image_url = request.build_absolute_uri(doc.file.url) if request else doc.file.url
                                car_images.append({
                                    'id': doc.id,
                                    'url': image_url,
                                    'type': doc.document_type.name if doc.document_type else 'Unknown',
                                    'filename': doc.file.name
                                })
                    except Exception as img_error:
                        print(f"Error processing image {doc.id}: {str(img_error)}")
                        continue
            return car_images
        except Exception as e:
            print(f"Error getting car images: {str(e)}")
            return []

    def _send_trip_progress_notification(self, rental, progress_type):
        """Send trip progress notifications"""
        try:
            from notifications.models import Notification
            
            progress_messages = {
                'halfway': {
                    'title': "⏰ Halfway Through Trip",
                    'message': f"Hello {rental.renter.first_name}! You've reached the halfway point of your trip 🎯\n\n💡 Tip: Make sure everything is going well"
                },
                'near_end': {
                    'title': "🏁 Trip Ending Soon",
                    'message': f"Hello {rental.renter.first_name}! You're approaching the end of your trip ⏰\n\n💡 Tip: Start heading to the dropoff location"
                },
                'successful_trip': {
                    'title': "🎉 Successful Trip!",
                    'message': f"Congratulations {rental.renter.first_name}! You've completed your trip successfully 🎯\n\n💡 Tip: Don't forget to rate your experience to improve our service"
                }
            }
            
            progress_info = progress_messages.get(progress_type, {
                'title': "📊 Trip Update",
                'message': f"Update on your trip: {progress_type}"
            })
            
            notification_data = {
                "rentalId": rental.id,
                "progressType": progress_type,
                "timestamp": timezone.now().isoformat(),
                "event": "trip_progress"
            }
            
            Notification.objects.create(  # type: ignore
                receiver=rental.renter,
                title=progress_info['title'],
                message=progress_info['message'],
                notification_type="PROGRESS",
                priority="MEDIUM",
                data=notification_data,
                navigation_id="TRIP_PROGRESS"
            )
            
            print(f"✅ Trip progress notification sent for {progress_type}")
            
        except Exception as e:
            print(f"❌ Error sending trip progress notification: {e}")

    @action(detail=True, methods=['post'])
    def renter_return_handover(self, request, pk=None):
        rental = self.get_object()
        contract = rental.contract
        if contract.renter_return_done:
            return Response({'error_code': 'RENTER_RETURN_HANDOVER_ALREADY_DONE', 'error_message': 'Renter return handover has already been completed and cannot be repeated.'}, status=400)
        payment = rental.payment
        odometer_image = request.FILES.get('odometer_image')
        odometer_value = request.data.get('odometer_value')
        car_image = request.FILES.get('car_image')
        notes = request.data.get('notes', '')
        if not odometer_image or not odometer_value:
            return Response({'error_code': 'ODOMETER_END_REQUIRED', 'error_message': 'End odometer image and reading are required.'}, status=400)
        if not car_image:
            return Response({'error_code': 'CAR_IMAGE_REQUIRED', 'error_message': 'Car image is required.'}, status=400)
        SelfDriveOdometerImage.objects.create(rental=rental, image=odometer_image, value=odometer_value, type='end')
        from .models import SelfDriveCarImage
        SelfDriveCarImage.objects.create(rental=rental, image=car_image, type='return', uploaded_by='renter', notes=notes)
        contract.renter_return_done = True
        contract.renter_return_done_at = timezone.now()
        contract.save()
        SelfDriveRentalLog.objects.create(rental=rental, action='return_handover_renter', user=request.user, details=f'Return handover (renter): notes={notes}')
        return Response({'status': 'Renter return handover complete.'})

    @action(detail=True, methods=['post'])
    def owner_return_handover(self, request, pk=None):
        rental = self.get_object()
        contract = rental.contract
        # Owner handover can only be done after renter handover
        if not contract.renter_return_done:
            return Response({'error_code': 'RENTER_HANDOVER_REQUIRED', 'error_message': 'Renter must return the car first.'}, status=400)
        if contract.owner_return_done:
            return Response({'error_code': 'OWNER_RETURN_HANDOVER_ALREADY_DONE', 'error_message': 'Owner return handover has already been completed and cannot be repeated.'}, status=400)
        notes = request.data.get('notes', '')
        payment = rental.payment
        # --- لا تغير أي شيء في الكونتراكت هنا ---
        if payment.payment_method == 'cash':
            confirm_excess_cash = request.data.get('confirm_excess_cash')
            if payment.excess_amount > 0:
                if payment.excess_paid_status != 'Paid':
                    if str(confirm_excess_cash).lower() == 'true':
                        payment.excess_paid_status = 'Paid'
                        payment.excess_paid_at = timezone.now()
                        payment.save()
                    else:
                        return Response({'error_code': 'EXCESS_CASH_CONFIRM_REQUIRED', 'error_message': 'يجب على المالك تأكيد استلام الزيادة كاش عبر confirm_excess_cash=true.'}, status=400)
        else:
            if payment.remaining_paid_status != 'Paid':
                return Response({'error_code': 'REMAINING_NOT_PAID', 'error_message': 'يجب دفع باقي المبلغ إلكترونياً قبل إنهاء تسليم المالك.'}, status=400)
            if payment.excess_amount > 0 and payment.excess_paid_status != 'Paid':
                return Response({'error_code': 'EXCESS_NOT_PAID', 'error_message': 'يجب دفع الزيادة إلكترونيًا قبل إنهاء تسليم المالك.'}, status=400)
        # --- بعد التحقق فقط، نفذ كل عمليات الحفظ ---
        contract.owner_return_done = True
        contract.owner_return_done_at = timezone.now()
        contract.save()
        SelfDriveRentalLog.objects.create(rental=rental, action='return_handover_owner', user=request.user, details=f'Return handover (owner): notes={notes}')
        old_status = rental.status
        rental.status = 'Finished'
        rental.save()
        if hasattr(rental, 'breakdown'):
            rental.breakdown.actual_dropoff_time = timezone.now()
            rental.breakdown.save()
        SelfDriveRentalStatusHistory.objects.create(rental=rental, old_status=old_status, new_status='Finished', changed_by=request.user)
        # خصم عمولة المنصة من محفظة المالك إذا كانت الرحلة كاش
        if payment.payment_method == 'cash':
            owner = rental.car.owner
            owner_wallet = Wallet.objects.get(user=owner)
            platform_commission = getattr(rental.breakdown, 'platform_earnings', 0)
            if platform_commission > 0:
                owner_wallet.deduct_funds(Decimal(str(platform_commission)))
                commission_type, _ = TransactionType.objects.get_or_create(name='Platform Commission', defaults={'is_credit': False})
                WalletTransaction.objects.create(
                    wallet=owner_wallet,
                    transaction_type=commission_type,
                    amount=Decimal(str(platform_commission)),
                    balance_before=owner_wallet.balance + Decimal(str(platform_commission)),
                    balance_after=owner_wallet.balance,
                    status='completed',
                    description=f'خصم عمولة المنصة لرحلة #{rental.id}',
                    reference_id=str(rental.id),
                    reference_type='selfdrive_rental'
                )
                if owner_wallet.balance < -1000:
                    SelfDriveRentalLog.objects.create(
                        rental=rental,
                        action='trip_finished',
                        user=owner,
                        details='تحذير: رصيد محفظة المالك أقل من -1000. يجب الشحن لاستقبال حجوزات جديدة.'
                    )
        # إضافة أرباح السائق إلى محفظة المالك إذا كانت الرحلة إلكترونية
        elif payment.payment_method in ['visa', 'wallet']:
            owner = rental.car.owner
            owner_wallet = Wallet.objects.get(user=owner)
            driver_earnings = getattr(rental.breakdown, 'driver_earnings', 0)
            if driver_earnings > 0:
                owner_wallet.add_funds(Decimal(str(driver_earnings)))
                earnings_type, _ = TransactionType.objects.get_or_create(name='Driver Earnings', defaults={'is_credit': True})
                WalletTransaction.objects.create(
                    wallet=owner_wallet,
                    transaction_type=earnings_type,
                    amount=Decimal(str(driver_earnings)),
                    balance_before=owner_wallet.balance - Decimal(str(driver_earnings)),
                    balance_after=owner_wallet.balance,
                    status='completed',
                    description=f'إضافة أرباح السائق لرحلة #{rental.id}',
                    reference_id=str(rental.id),
                    reference_type='selfdrive_rental'
                )
                if owner_wallet.balance < -1000:
                    SelfDriveRentalLog.objects.create(
                        rental=rental,
                        action='trip_finished',
                        user=owner,
                        details='تحذير: رصيد محفظة المالك أقل من -1000. يجب الشحن لاستقبال حجوزات جديدة.'
                    )
        # Build excess details and payment info
        breakdown = getattr(rental, 'breakdown', None)
        excess_details = None
        if breakdown:
            excess_details = {
                'extra_km_fee': breakdown.extra_km_fee,
                'late_fee': breakdown.late_fee,
                'extra_km': breakdown.extra_km,
                'extra_km_cost': breakdown.extra_km_cost,
                'late_days': breakdown.late_days,
                'late_fee_per_day': breakdown.daily_price,
                'late_fee_service_percent': 30
            }
        excess_payment = {
            'excess_paid_status': payment.excess_paid_status,
            'excess_paid_at': payment.excess_paid_at,
            'excess_transaction_id': payment.excess_transaction_id,
            'payment_method': payment.payment_method
        }
        return Response({
            'status': 'Owner return handover complete. Trip finished.',
            'excess_amount': payment.excess_amount,
            'excess_details': excess_details,
            'excess_payment': excess_payment
        })

    @action(detail=True, methods=['get'])
    def get_last_location(self, request, pk=None):
        rental = self.get_object()
        last_location = rental.live_locations.order_by('-timestamp').first()
        if not last_location:
            return Response({'error_code': 'NO_LOCATION', 'error_message': 'لا يوجد موقع مسجل لهذه الرحلة.'}, status=404)
        return Response({
            'latitude': last_location.latitude,
            'longitude': last_location.longitude,
            'timestamp': last_location.timestamp
        })

    # @action(detail=True, methods=['post'])
    # def request_location(self, request, pk=None):
    #     rental = self.get_object()
    #     # تخيلي: حفظ طلب الموقع
    #     lat = request.data.get('latitude')
    #     lng = request.data.get('longitude')
    #     SelfDriveLiveLocation.objects.create(rental=rental, latitude=lat, longitude=lng)
    #     SelfDriveRentalLog.objects.create(rental=rental, action='location_requested', user=request.user, details=f'Location requested: {lat}, {lng}')
    #     return Response({'status': 'تم حفظ الموقع.'})
    
    @action(detail=True, methods=['post'])
    def request_location(self, request, pk=None):
        rental = self.get_object()
        # استخدم الدالة الوهمية لجلب إحداثيات عشوائية
        lat, lng = get_random_lat_lng()
        SelfDriveLiveLocation.objects.create(rental=rental, latitude=lat, longitude=lng)
        SelfDriveRentalLog.objects.create(
            rental=rental,
            action='location_requested',
            user=request.user,
            details=f'Location requested: {lat}, {lng}'
        )
        return Response({'status': 'تم حفظ الموقع.', 'latitude': lat, 'longitude': lng})
    
    @action(detail=True, methods=['post'])
    # def renter_dropoff_handover(self, request, pk=None):
    #     rental = self.get_object()
    #     contract = rental.contract
    #     if contract.renter_return_done:
    #         return Response({'error_code': 'RENTER_RETURN_HANDOVER_ALREADY_DONE', 'error_message': 'تم تنفيذ تسليم المستأجر (نهاية الرحلة) بالفعل ولا يمكن تكراره.'}, status=400)
    #     payment = rental.payment
    #     odometer_image = request.FILES.get('odometer_image')
    #     odometer_value = request.data.get('odometer_value')
    #     car_image = request.FILES.get('car_image')
    #     notes = request.data.get('notes', '')
    #     if not odometer_image or not odometer_value:
    #         return Response({'error_code': 'ODOMETER_END_REQUIRED', 'error_message': 'صورة وقراءة عداد النهاية مطلوبة.'}, status=400)
    #     if not car_image:
    #         return Response({'error_code': 'CAR_IMAGE_REQUIRED', 'error_message': 'يجب رفع صورة العربية عند التسليم.'}, status=400)
    #     from .models import SelfDriveOdometerImage, SelfDriveCarImage
    #     SelfDriveOdometerImage.objects.create(
    #         rental=rental,
    #         image=odometer_image,
    #         value=float(odometer_value),
    #         type='end'
    #     )
    #     SelfDriveCarImage.objects.create(rental=rental, image=car_image, type='return', uploaded_by='renter', notes=notes)
    #     actual_dropoff_time = timezone.now()
    #     try:
    #         payment = calculate_selfdrive_payment(rental, actual_dropoff_time=actual_dropoff_time)
    #     except ValueError as e:
    #         return Response({'error_code': 'INVALID_DATA', 'error_message': str(e)}, status=400)
    #     # إذا كان هناك زيادة يجب دفعها إلكترونيًا
    #     if payment.excess_amount > 0 and payment.payment_method in ['visa', 'wallet'] and payment.excess_paid_status != 'Paid':
    #         from payments.services.payment_gateway import simulate_payment_gateway
    #         payment_response = simulate_payment_gateway(
    #             amount=payment.excess_amount,
    #             payment_method=payment.payment_method,
    #             user=request.user
    #         )
    #         if payment_response.success:
    #             payment.excess_paid_status = 'Paid'
    #             payment.excess_paid_at = timezone.now()
    #             payment.excess_transaction_id = payment_response.transaction_id
    #             payment.save()
    #             from .models import SelfDriveRentalLog
    #             SelfDriveRentalLog.objects.create(
    #                 rental=payment.rental,
    #                 action='payment',
    #                 user=request.user,
    #                 details=f'Excess payment: {payment_response.transaction_id}'
    #             )
    #         else:
    #             return Response({'error_code': 'EXCESS_PAYMENT_FAILED', 'error_message': payment_response.message}, status=400)
    #     contract.renter_return_done = True
    #     contract.renter_return_done_at = actual_dropoff_time
    #     contract.save()
    #     SelfDriveRentalLog.objects.create(rental=rental, action='renter_dropoff_handover', user=request.user, details='Renter did dropoff handover. Excess calculated.')
    #     # Build excess details and payment info
    #     breakdown = getattr(rental, 'breakdown', None)
    #     excess_details = None
    #     if breakdown:
    #         excess_details = {
    #             'extra_km_fee': breakdown.extra_km_fee,
    #             'late_fee': breakdown.late_fee,
    #             'extra_km': breakdown.extra_km,
    #             'extra_km_cost': breakdown.extra_km_cost,
    #             'late_days': breakdown.late_days,
    #             'late_fee_per_day': breakdown.daily_price,
    #             'late_fee_service_percent': 30
    #         }
    #     excess_payment = {
    #         'excess_paid_status': payment.excess_paid_status,
    #         'excess_paid_at': payment.excess_paid_at,
    #         'excess_transaction_id': payment.excess_transaction_id,
    #         'payment_method': payment.payment_method
    #     }
    #     return Response({
    #         'status': 'تم تسليم السيارة من المستأجر (نهاية الرحلة).',
    #         'excess_amount': payment.excess_amount,
    #         'excess_details': excess_details,
    #         'excess_payment': excess_payment
    #     })

    @action(detail=True, methods=['post'])
    def renter_dropoff_handover(self, request, pk=None):
        rental = self.get_object()
        contract = rental.contract
        if contract.renter_return_done:
            return Response({'error_code': 'RENTER_RETURN_HANDOVER_ALREADY_DONE', 'error_message': 'تم تنفيذ تسليم المستأجر (نهاية الرحلة) بالفعل ولا يمكن تكراره.'}, status=400)
        payment = rental.payment
        odometer_image = request.FILES.get('odometer_image')
        odometer_value = request.data.get('odometer_value')
        car_image = request.FILES.get('car_image')
        notes = request.data.get('notes', '')
        if not odometer_image or not odometer_value:
            return Response({'error_code': 'ODOMETER_END_REQUIRED', 'error_message': 'صورة وقراءة عداد النهاية مطلوبة.'}, status=400)
        if not car_image:
            return Response({'error_code': 'CAR_IMAGE_REQUIRED', 'error_message': 'يجب رفع صورة العربية عند التسليم.'}, status=400)
        from .models import SelfDriveOdometerImage, SelfDriveCarImage

        # --- تعديل التسمية ---
        car_identifier = getattr(rental.car, 'plate_number', None) or getattr(rental.car, 'model', 'car')
        car_identifier = str(car_identifier).replace(' ', '_')
        rental_type = 'return'
        # car image
        car_image.name = f"{car_identifier}_{rental_type}_car_{rental.id}.png"
        SelfDriveCarImage.objects.create(rental=rental, image=car_image, type=rental_type, uploaded_by='renter', notes=notes)
        # odometer image
        odometer_image.name = f"{car_identifier}_{rental_type}_odometer_{rental.id}.png"
        SelfDriveOdometerImage.objects.create(
            rental=rental,
            image=odometer_image,
            value=float(odometer_value),
            type='end'
        )

        actual_dropoff_time = timezone.now()
        try:
            payment = calculate_selfdrive_payment(rental, actual_dropoff_time=actual_dropoff_time)
        except ValueError as e:
            return Response({'error_code': 'INVALID_DATA', 'error_message': str(e)}, status=400)

        # الدفع الإلكتروني للزيادة بنفس منطق pickup
        paymob_details = None
        if payment.excess_amount > 0 and payment.payment_method in ['visa', 'wallet'] and payment.excess_paid_status != 'Paid':
            if payment.payment_method == 'visa':
                selected_card = getattr(rental, 'selected_card', None)
                if not selected_card:
                    return Response({'error_code': 'NO_SELECTED_CARD', 'error_message': 'لم يتم اختيار كارت فيزا لهذا الحجز.'}, status=400)
                if selected_card.user != request.user:
                    return Response({'error_code': 'CARD_NOT_OWNED', 'error_message': 'الكارت المختار لا يخصك.'}, status=403)
                from payments.services.payment_gateway import pay_with_saved_card_gateway
                amount_cents = int(round(float(payment.excess_amount) * 100))
                result = pay_with_saved_card_gateway(amount_cents, request.user, selected_card.token)
                payment.excess_paid_status = 'Paid' if result['success'] else 'Pending'
                payment.excess_paid_at = timezone.now() if result['success'] else None
                payment.excess_transaction_id = result['transaction_id']
                payment.save()
                from .models import SelfDriveRentalLog
                SelfDriveRentalLog.objects.create(
                    rental=payment.rental,
                    action='payment',
                    user=request.user,
                    details=f'Excess payment: {result}'
                )
                if not result['success']:
                    return Response({'error_code': 'EXCESS_PAYMENT_FAILED', 'error_message': result['message'], 'paymob_details': result}, status=400)
                paymob_details = result
            else:
                # محفظة أو طرق أخرى
                from payments.services.payment_gateway import simulate_payment_gateway
                payment_response = simulate_payment_gateway(
                    amount=payment.excess_amount,
                    payment_method=payment.payment_method,
                    user=request.user
                )
                if payment_response.success:
                    payment.excess_paid_status = 'Paid'
                    payment.excess_paid_at = timezone.now()
                    payment.excess_transaction_id = payment_response.transaction_id
                    payment.save()
                    from .models import SelfDriveRentalLog
                    SelfDriveRentalLog.objects.create(
                        rental=payment.rental,
                        action='payment',
                        user=request.user,
                        details=f'Excess payment: {payment_response.transaction_id}'
                    )
                else:
                    return Response({'error_code': 'EXCESS_PAYMENT_FAILED', 'error_message': payment_response.message}, status=400)

        contract.renter_return_done = True
        contract.renter_return_done_at = actual_dropoff_time
        contract.save()
        SelfDriveRentalLog.objects.create(rental=rental, action='renter_dropoff_handover', user=request.user, details='Renter did dropoff handover. Excess calculated.')
        # Build excess details and payment info
        breakdown = getattr(rental, 'breakdown', None)
        excess_details = None
        if breakdown:
            excess_details = {
                'extra_km_fee': breakdown.extra_km_fee,
                'late_fee': breakdown.late_fee,
                'extra_km': breakdown.extra_km,
                'extra_km_cost': breakdown.extra_km_cost,
                'late_days': breakdown.late_days,
                'late_fee_per_day': breakdown.daily_price,
                'late_fee_service_percent': 30
            }
        excess_payment = {
            'excess_paid_status': payment.excess_paid_status,
            'excess_paid_at': payment.excess_paid_at,
            'excess_transaction_id': payment.excess_transaction_id,
            'payment_method': payment.payment_method
        }
        return Response({
            'status': 'تم تسليم السيارة من المستأجر (نهاية الرحلة).',
            'car_image': car_image.name,
            'odometer_image': odometer_image.name,
            'excess_amount': payment.excess_amount,
            'excess_details': excess_details,
            'excess_payment': excess_payment,
            'paymob_details': paymob_details
        })

    @action(detail=True, methods=['post'])
    def owner_dropoff_handover(self, request, pk=None):
        rental = self.get_object()
        contract = rental.contract
        
        # لا يمكن تنفيذ هاند أوفر المالك إلا بعد هاند أوفر المستأجر
        if not contract.renter_return_done:
            return Response({'error_code': 'RENTER_HANDOVER_REQUIRED', 'error_message': 'يجب أن يقوم المستأجر بتسليم السيارة أولاً.'}, status=400)
        if contract.owner_return_done:
            return Response({'error_code': 'OWNER_RETURN_HANDOVER_ALREADY_DONE', 'error_message': 'تم تنفيذ تسليم المالك (نهاية الرحلة) بالفعل ولا يمكن تكراره.'}, status=400)
        notes = request.data.get('notes', '')
        payment = rental.payment

        # تحقق من عدم السماح بتأكيد الكاش في الدفع الإلكتروني
        confirm_excess_cash = request.data.get('confirm_excess_cash')
        if payment.payment_method in ['visa', 'wallet']:
            if confirm_excess_cash is not None:
                return Response({'error_code': 'CASH_NOT_ALLOWED', 'error_message': 'الدفع إلكتروني ولا يمكن تأكيد استلام كاش.'}, status=400)
        # --- لا تغير أي شيء في الكونتراكت هنا ---
        if payment.payment_method == 'cash':
            confirm_excess_cash = request.data.get('confirm_excess_cash')
            if payment.excess_amount > 0:
                if payment.excess_paid_status != 'Paid':
                    if str(confirm_excess_cash).lower() == 'true':
                        payment.excess_paid_status = 'Paid'
                        payment.excess_paid_at = timezone.now()
                        payment.excess_transaction_id = f'excess_cash_{rental.id}'  # محاكاة معرف المعاملة
 
                        payment.save()
                    else:
                        return Response({'error_code': 'EXCESS_CASH_CONFIRM_REQUIRED', 'error_message': 'يجب على المالك تأكيد استلام الزيادة كاش عبر confirm_excess_cash=true.'}, status=400)
        else:
            if payment.remaining_paid_status != 'Paid':
                return Response({'error_code': 'REMAINING_NOT_PAID', 'error_message': 'يجب دفع باقي المبلغ إلكترونياً قبل إنهاء تسليم المالك.'}, status=400)
            if payment.excess_amount > 0 and payment.excess_paid_status != 'Paid':
                return Response({'error_code': 'EXCESS_NOT_PAID', 'error_message': 'يجب دفع الزيادة إلكترونيًا قبل إنهاء تسليم المالك.'}, status=400)
        # --- بعد التحقق فقط، نفذ كل عمليات الحفظ ---
        contract.owner_return_done = True
        contract.owner_return_done_at = timezone.now()
        contract.save()
        SelfDriveRentalLog.objects.create(rental=rental, action='return_handover_owner', user=request.user, details=f'Return handover (owner): notes={notes}')
        old_status = rental.status
        rental.status = 'Finished'
        rental.save()
        if hasattr(rental, 'breakdown'):
            rental.breakdown.actual_dropoff_time = timezone.now()
            rental.breakdown.save()
        SelfDriveRentalStatusHistory.objects.create(rental=rental, old_status=old_status, new_status='Finished', changed_by=request.user)
        # خصم عمولة المنصة من محفظة المالك إذا كانت الرحلة كاش
        if payment.payment_method == 'cash':
            owner = rental.car.owner
            owner_wallet = Wallet.objects.get(user=owner)
            platform_commission = getattr(rental.breakdown, 'platform_earnings', 0)
            if platform_commission > 0:
                owner_wallet.deduct_funds(Decimal(str(platform_commission)))
                commission_type, _ = TransactionType.objects.get_or_create(name='Platform Commission', defaults={'is_credit': False})
                WalletTransaction.objects.create(
                    wallet=owner_wallet,
                    transaction_type=commission_type,
                    amount=Decimal(str(platform_commission)),
                    balance_before=owner_wallet.balance + Decimal(str(platform_commission)),
                    balance_after=owner_wallet.balance,
                    status='completed',
                    description=f'خصم عمولة المنصة لرحلة #{rental.id}',
                    reference_id=str(rental.id),
                    reference_type='selfdrive_rental'
                )
                if owner_wallet.balance < -1000:
                    SelfDriveRentalLog.objects.create(
                        rental=rental,
                        action='trip_finished',
                        user=owner,
                        details='تحذير: رصيد محفظة المالك أقل من -1000. يجب الشحن لاستقبال حجوزات جديدة.'
                    )
        # إضافة أرباح السائق إلى محفظة المالك إذا كانت الرحلة إلكترونية
        elif payment.payment_method in ['visa', 'wallet']:
            owner = rental.car.owner
            owner_wallet = Wallet.objects.get(user=owner)
            driver_earnings = getattr(rental.breakdown, 'driver_earnings', 0)
            if driver_earnings > 0:
                owner_wallet.add_funds(Decimal(str(driver_earnings)))
                earnings_type, _ = TransactionType.objects.get_or_create(name='Driver Earnings', defaults={'is_credit': True})
                WalletTransaction.objects.create(
                    wallet=owner_wallet,
                    transaction_type=earnings_type,
                    amount=Decimal(str(driver_earnings)),
                    balance_before=owner_wallet.balance - Decimal(str(driver_earnings)),
                    balance_after=owner_wallet.balance,
                    status='completed',
                    description=f'إضافة أرباح السائق لرحلة #{rental.id}',
                    reference_id=str(rental.id),
                    reference_type='selfdrive_rental'
                )
                if owner_wallet.balance < -1000:
                    SelfDriveRentalLog.objects.create(
                        rental=rental,
                        action='trip_finished',
                        user=owner,
                        details='تحذير: رصيد محفظة المالك أقل من -1000. يجب الشحن لاستقبال حجوزات جديدة.'
                    )
        # Build excess details and payment info
        breakdown = getattr(rental, 'breakdown', None)
        excess_details = None
        if breakdown:
            excess_details = {
                'extra_km_fee': breakdown.extra_km_fee,
                'late_fee': breakdown.late_fee,
                'extra_km': breakdown.extra_km,
                'extra_km_cost': breakdown.extra_km_cost,
                'late_days': breakdown.late_days,
                'late_fee_per_day': breakdown.daily_price,
                'late_fee_service_percent': 30
            }
        excess_payment = {
            'excess_paid_status': payment.excess_paid_status,
            'excess_paid_at': payment.excess_paid_at,
            'excess_transaction_id': payment.excess_transaction_id,
            'payment_method': payment.payment_method
        }
        return Response({
            'status': 'Owner return handover complete. Trip finished.',
            'excess_amount': payment.excess_amount,
            'excess_details': excess_details,
            'excess_payment': excess_payment
        })

    @action(detail=True, methods=['post'])
    def finish_trip(self, request, pk=None):
        rental = self.get_object()
        if rental.status == 'Finished':
            return Response({'error_code': 'ALREADY_FINISHED', 'error_message': 'تم إنهاء الرحلة بالفعل.'}, status=400)
        old_status = rental.status
        rental.status = 'Finished'
        rental.save()
        SelfDriveRentalLog.objects.create(rental=rental, action='trip_finished', user=request.user, details='Trip finished.')
        SelfDriveRentalStatusHistory.objects.create(rental=rental, old_status=old_status, new_status='Finished', changed_by=request.user)
        return Response({'status': 'تم إنهاء الرحلة.'})

    @action(detail=True, methods=['post'])
    def cancel_rental(self, request, pk=None):
        rental = self.get_object()
        contract = rental.contract
        # الإلغاء فقط من المالك
        if rental.car.owner != request.user:
            return Response({'error_code': 'NOT_OWNER', 'error_message': 'فقط مالك السيارة يمكنه إلغاء الحجز.'}, status=403)
        # لا يمكن الإلغاء إذا تم أي handover
        if contract.renter_pickup_done or contract.owner_pickup_done or contract.renter_return_done or contract.owner_return_done:
            return Response({'error_code': 'HANDOVER_ALREADY_DONE', 'error_message': 'لا يمكن إلغاء الحجز بعد بدء أو إنهاء أي handover.'}, status=400)
        if rental.status == 'Canceled':
            return Response({'error_code': 'ALREADY_CANCELED', 'error_message': 'تم إلغاء الحجز بالفعل.'}, status=400)
        # إذا كان الديبوزيت مدفوع يتم رده
        payment = rental.payment
        if payment.deposit_paid_status == 'Paid' and not payment.deposit_refunded:
            from wallets.models import Wallet, WalletTransaction, TransactionType
            renter = rental.renter
            renter_wallet = Wallet.objects.get(user=renter)
            deposit_amount = Decimal(str(payment.deposit_amount))
            # أضف العربون للمحفظة
            renter_wallet.add_funds(deposit_amount)
            # سجل WalletTransaction
            refund_type, _ = TransactionType.objects.get_or_create(name='Deposit Refund', defaults={'is_credit': True})
            WalletTransaction.objects.create(
                wallet=renter_wallet,
                transaction_type=refund_type,
                amount=deposit_amount,
                balance_before=renter_wallet.balance - deposit_amount,
                balance_after=renter_wallet.balance,
                status='completed',
                description=f'استرداد العربون لإلغاء رحلة #{rental.id} من المالك',
                reference_id=str(rental.id),
                reference_type='selfdrive_rental'
            )
            # حدث حالة الدفع
            from django.utils import timezone
            payment.deposit_refunded = True
            payment.deposit_refunded_at = timezone.now()
            payment.deposit_refund_transaction_id = f'REFUND-{rental.id}-{int(payment.deposit_refunded_at.timestamp())}'
            payment.deposit_paid_status = 'Refunded'
            payment.save()
        old_status = rental.status
        rental.status = 'Canceled'
        rental.save()
        SelfDriveRentalLog.objects.create(rental=rental, action='canceled', user=request.user, details='Rental canceled by owner.')
        SelfDriveRentalStatusHistory.objects.create(rental=rental, old_status=old_status, new_status='Canceled', changed_by=request.user)
        # Build deposit refund details
        if payment.deposit_paid_status != 'Paid':
            refund_note = 'لم يتم دفع الديبوزيت أصلاً، لذلك لا يوجد ما يُرد.'
        elif payment.deposit_refunded:
            refund_note = 'تم رد الديبوزيت بنجاح.'
        else:
            refund_note = 'تم دفع الديبوزيت، وسيتم رده قريباً.'
        deposit_refund = {
            'deposit_amount': payment.deposit_amount,
            'deposit_refunded': payment.deposit_refunded,
            'deposit_refunded_at': payment.deposit_refunded_at,
            'deposit_refund_transaction_id': payment.deposit_refund_transaction_id,
            'refund_status': 'تم الرد' if payment.deposit_refunded else 'لم يتم الرد بعد',
            'refund_note': refund_note
        }
        return Response({'status': 'تم إلغاء الحجز وتم رد الديبوزيت (إن وجد).', 'deposit_refund': deposit_refund})

    @action(detail=True, methods=['post'])
    def confirm_remaining_cash_received(self, request, pk=None):
        rental = self.get_object()
        payment = rental.payment
        if payment.payment_method != 'cash':
            return Response({'error_code': 'NOT_CASH', 'error_message': 'الدفع ليس نقدي.'}, status=400)
        if payment.remaining_paid_status == 'Confirmed':
            return Response({'error_code': 'ALREADY_CONFIRMED', 'error_message': 'تم تأكيد استلام باقي المبلغ كاش بالفعل.'}, status=400)
        payment.remaining_paid_status = 'Confirmed'
        payment.remaining_paid_at = timezone.now()
        payment.save()
        SelfDriveRentalLog.objects.create(rental=rental, action='payment', user=request.user, details='Confirmed receiving remaining cash.')
        return Response({'status': 'تم تأكيد استلام باقي المبلغ كاش.'})

    @action(detail=True, methods=['post'])
    def confirm_excess_cash_received(self, request, pk=None):
        rental = self.get_object()
        payment = rental.payment
        if payment.payment_method != 'cash':
            return Response({'error_code': 'NOT_CASH', 'error_message': 'الدفع ليس نقدي.'}, status=400)
        if payment.excess_paid_status == 'Paid':
            return Response({'error_code': 'ALREADY_CONFIRMED', 'error_message': 'تم تأكيد استلام الزيادة كاش بالفعل.'}, status=400)
        payment.excess_paid_status = 'Paid'
        payment.excess_paid_at = timezone.now()
        payment.save()
        SelfDriveRentalLog.objects.create(rental=rental, action='payment', user=request.user, details='Confirmed receiving excess cash.')
        return Response({'status': 'تم تأكيد استلام الزيادة كاش.'})

    @action(detail=True, methods=['get'])
    def summary(self, request, pk=None):
        rental = self.get_object()
        serializer = SelfDriveRentalSerializer(rental)
        return Response(serializer.data)

    @action(detail=True, methods=['get'], url_path='review_for_owner')
    def review_for_owner(self, request, pk=None):
        """
        يعرض كل تفاصيل الحجز للمالك قبل القبول أو الرفض (self-drive)
        """
        rental = self.get_object()
        user = request.user
        
        # تحقق أن المستخدم هو المالك
        if rental.car.owner != user:
            return Response({
                'error_code': 'NOT_OWNER',
                'error_message': 'فقط مالك السيارة يمكنه مراجعة تفاصيل الحجز.'
            }, status=403)
        
        # بيانات المستأجر
        renter = rental.renter
        renter_info = {
            'id': renter.id,
            'name': renter.get_full_name() or renter.email,
            'email': renter.email,
            'phone': renter.phone_number,
            'avg_rating': getattr(renter, 'avg_rating', None),
            'total_reviews': getattr(renter, 'total_reviews', None),
            'reports_count': getattr(renter, 'reports_count', None),
            'national_id': getattr(renter, 'national_id', None),
        }
        
        # بيانات السيارة
        car = rental.car
        car_info = {
            'id': car.id,
            'brand': car.brand,
            'model': car.model,
            'year': car.year,
            'category': getattr(car, 'category', None),
            'type': getattr(car, 'car_type', None),
            'plate_number': getattr(car, 'plate_number', None),
        }
        
        # بيانات التكلفة
        breakdown = getattr(rental, 'breakdown', None)
        cost_info = {
            'num_days': breakdown.num_days if breakdown else None,
            'daily_price': float(breakdown.daily_price) if breakdown else None,
            'base_cost': float(breakdown.base_cost) if breakdown else None,
            'ctw_fee': float(breakdown.ctw_fee) if breakdown else None,
            'initial_cost': float(breakdown.initial_cost) if breakdown else None,
            'final_cost': float(breakdown.final_cost) if breakdown else None,
            'allowed_km': float(breakdown.allowed_km) if breakdown else None,
            'extra_km_cost': float(breakdown.extra_km_cost) if breakdown else None,
            'commission_rate': float(breakdown.commission_rate) if breakdown else None,
            'platform_earnings': float(breakdown.platform_earnings) if breakdown else None,
            'driver_earnings': float(breakdown.driver_earnings) if breakdown else None,
        }
        
        # بيانات الدفع
        payment = getattr(rental, 'payment', None)
        payment_info = {
            'deposit_amount': float(payment.deposit_amount) if payment else None,
            'deposit_paid_status': payment.deposit_paid_status if payment else None,
            'remaining_amount': float(payment.remaining_amount) if payment else None,
            'remaining_paid_status': payment.remaining_paid_status if payment else None,
            'payment_method': payment.payment_method if payment else None,
            'rental_total_amount': float(payment.rental_total_amount) if payment else None,
        }
        
        # بيانات العداد
        odometer_images = rental.odometer_images.all()
        odometer_info = [
            {
                'id': img.id,
                'type': img.type,
                'value': float(img.value) if img.value else None,
                'image_url': img.image.url if img.image else None,
                'uploaded_at': img.uploaded_at,
            }
            for img in odometer_images
        ]
        
        # بيانات العقد
        contract = getattr(rental, 'contract', None)
        contract_info = {
            'signed_by_renter': contract.signed_by_renter if contract else False,
            'signed_by_owner': contract.signed_by_owner if contract else False,
            'signed_at': contract.signed_at if contract else None,
            'renter_pickup_done': contract.renter_pickup_done if contract else False,
            'owner_pickup_done': contract.owner_pickup_done if contract else False,
            'renter_return_done': contract.renter_return_done if contract else False,
            'owner_return_done': contract.owner_return_done if contract else False,
        }
        
        # بيانات الموقع
        live_location = rental.live_locations.last()
        location_info = {
            'latitude': float(live_location.latitude) if live_location else None,
            'longitude': float(live_location.longitude) if live_location else None,
            'timestamp': live_location.timestamp if live_location else None,
        }
        
        # الرد النهائي - النقاط الأساسية فقط
        return Response({
            'rental_id': rental.id,
            'status': rental.status,
            'start_date': rental.start_date,
            'end_date': rental.end_date,
            'pickup_address': rental.pickup_address,
            'dropoff_address': rental.dropoff_address,
            'renter_name': renter.get_full_name() or renter.email,
            'renter_phone': renter.phone_number,
            'renter_rating': getattr(renter, 'avg_rating', 0),
            'car_info': f"{car.brand} {car.model} {car.year}",
            'num_days': breakdown.num_days if breakdown else 0,
            'daily_price': float(breakdown.daily_price) if breakdown else 0,
            'total_cost': float(breakdown.final_cost) if breakdown else 0,
            'deposit_amount': float(payment.deposit_amount) if payment else 0,
            'driver_earnings': float(breakdown.driver_earnings) if breakdown else 0,
            'can_confirm': rental.status == 'PendingOwnerConfirmation',
            'can_reject': rental.status == 'PendingOwnerConfirmation'
        })

def get_random_lat_lng():
    # توليد إحداثيات عشوائية داخل مصر (مثال)
    lat = round(random.uniform(22.0, 31.0), 6)
    lng = round(random.uniform(25.0, 35.0), 6)
    return lat, lng
def calculate_selfdrive_payment(rental, actual_dropoff_time=None):
    # تحقق من وجود سياسة الاستخدام
    usage_policy = getattr(rental.car, 'usage_policy', None)
    if not usage_policy:
        raise ValueError('سياسة استخدام السيارة غير موجودة. يرجى ضبط سياسة الاستخدام أولاً.')
    daily_km_limit = float(getattr(usage_policy, 'daily_km_limit', 0) or 0)
    extra_km_cost = float(getattr(usage_policy, 'extra_km_cost', 0) or 0)
    if daily_km_limit == 0 or extra_km_cost == 0:
        raise ValueError('حد الكيلومترات اليومي أو تكلفة الكيلو الزائد غير مضبوطة. يرجى ضبط سياسة الاستخدام للسيارة.')
    # تحقق من وجود صور العداد
    odometers = rental.odometer_images.all()
    start_odometer = odometers.filter(type='start').order_by('uploaded_at').first()
    end_odometer = odometers.filter(type='end').order_by('-uploaded_at').first()
    if not start_odometer or not end_odometer:
        raise ValueError('يجب رفع صورة عداد البداية والنهاية لحساب الزيادة.')
    km_used = max(0, float(end_odometer.value) - float(start_odometer.value))
    duration_days = (rental.end_date.date() - rental.start_date.date()).days + 1
    daily_price = float(getattr(rental.car.rental_options, 'daily_rental_price', 0) or 0)
    financials = calculate_selfdrive_financials(daily_price, duration_days)
    base_cost = float(financials['base_cost'])
    ctw_fee = float(financials['ctw_fee'])
    initial_cost = float(financials['final_cost'])
    allowed_km = duration_days * daily_km_limit
    extra_km = max(0, km_used - allowed_km)
    extra_km_fee = extra_km * extra_km_cost
    late_days = 0
    late_fee = 0
    if actual_dropoff_time and actual_dropoff_time > rental.end_date:
        time_diff = actual_dropoff_time - rental.end_date
        late_days = math.ceil(time_diff.total_seconds() / (24 * 3600))
        if late_days > 0:
            late_fee = late_days * daily_price
            late_fee += late_fee * 0.3  # زيادة 30% على رسوم التأخير
    total_extras_cost = extra_km_fee + late_fee
    final_cost = initial_cost + total_extras_cost
    commission_rate = 0.2
    platform_earnings = final_cost * commission_rate
    driver_earnings = final_cost - platform_earnings
    # استخدم update_or_create بدلاً من الحذف والإنشاء
    SelfDriveRentalBreakdown.objects.update_or_create(  # type: ignore
        rental=rental,
        defaults={
            'actual_dropoff_time': actual_dropoff_time,
            'num_days': duration_days,
            'daily_price': daily_price,
            'base_cost': base_cost,
            'ctw_fee': ctw_fee,
            'initial_cost': initial_cost,
            'allowed_km': allowed_km,
            'extra_km': extra_km,
            'extra_km_cost': extra_km_cost,
            'extra_km_fee': extra_km_fee,
            'late_days': late_days,
            'late_fee': late_fee,
            'total_extras_cost': total_extras_cost,
            'final_cost': final_cost,
            'commission_rate': commission_rate,
            'platform_earnings': platform_earnings,
            'driver_earnings': driver_earnings,
        }
    )
    payment, _ = SelfDrivePayment.objects.get_or_create(rental=rental)  # type: ignore
    # Separate excess from remaining
    excess_amount = extra_km_fee + late_fee
    payment.excess_amount = excess_amount
    payment.rental_total_amount = final_cost
    payment.remaining_amount = initial_cost - payment.deposit_amount  # Only the base remaining, not including excess
    payment.save()
    return payment

def check_and_start_trip(rental):
    contract = rental.contract
    payment = rental.payment
    has_start_odometer = rental.odometer_images.filter(type='start').exists()
    has_contract_image = bool(contract.owner_contract_image)
    if contract.renter_signed and contract.owner_signed and has_start_odometer and has_contract_image:
        if payment.payment_method in ['visa', 'wallet']:
            if payment.remaining_paid_status == 'Paid':
                rental.status = 'Ongoing'
                rental.save()
        else:
            if payment.remaining_paid_status == 'Confirmed':
                rental.status = 'Ongoing'
                rental.save()

def generate_contract_pdf(rental):
    # دالة وهمية: ترجع PDF بايتس بدون أي تنسيق خطأ
    return b'%%PDF-1.4\n%% Dummy contract PDF for rental %d\n%%%%EOF' % rental.id

def check_deposit_expiry(rental):
    payment = rental.payment
    if rental.status == 'DepositRequired' and payment.deposit_due_at and payment.deposit_paid_status != 'Paid':
        if timezone.now() > payment.deposit_due_at:
            rental.status = 'Canceled'
            rental.save()
            return True
    return False

def fake_payment(payment, user, payment_type='remaining'):
    """
    دالة دفع وهمية: تخصم من wallet أو تقبل فيزا وهميًا.
    ترجع (True, transaction_id) لو نجحت، (False, error_message) لو فشلت.
    """
    import random
    import string
    from django.utils import timezone
    # محاكاة الدفع الإلكتروني
    if payment_type == 'remaining':
        if payment.payment_method == 'wallet':
            wallet_balance = 999999  # عدلها حسب نظامك
            if wallet_balance < payment.remaining_amount:
                return False, 'رصيد المحفظة غير كافٍ.'
        transaction_id = 'FAKE-' + ''.join(random.choices(string.ascii_uppercase + string.digits, k=8))
        payment.remaining_paid_status = 'Paid'
        payment.remaining_paid_at = timezone.now()
        payment.remaining_transaction_id = transaction_id
        payment.save()
        from .models import SelfDriveRentalLog
        SelfDriveRentalLog.objects.create(rental=payment.rental, action='payment', user=user, details=f'Fake payment for remaining: {transaction_id}')  # type: ignore
        return True, transaction_id
    elif payment_type == 'excess':
        if payment.payment_method == 'wallet':
            wallet_balance = 999999
            if wallet_balance < payment.excess_amount:
                return False, 'رصيد المحفظة غير كافٍ.'
        transaction_id = 'FAKE-' + ''.join(random.choices(string.ascii_uppercase + string.digits, k=8))
        payment.excess_paid_status = 'Paid'
        payment.excess_paid_at = timezone.now()
        payment.excess_transaction_id = transaction_id
        payment.save()
        from .models import SelfDriveRentalLog
        SelfDriveRentalLog.objects.create(rental=payment.rental, action='payment', user=user, details=f'Fake payment for excess: {transaction_id}')  # type: ignore
        return True, transaction_id
    return False, 'نوع الدفع غير مدعوم.'

def fake_refund(payment, user):
    """
    دالة وهمية لرد الديبوزيت: تحدث حالة الديبوزيت وتضيف لوج وهمي.
    """
    from django.utils import timezone
    import random
    import string
    payment.deposit_refunded = True
    payment.deposit_refunded_at = timezone.now()
    payment.deposit_refund_transaction_id = 'REFUND-' + ''.join(random.choices(string.ascii_uppercase + string.digits, k=8))
    payment.deposit_paid_status = 'Refunded'
    payment.save()
    from .models import SelfDriveRentalLog
    SelfDriveRentalLog.objects.create(rental=payment.rental, action='deposit_refund', user=user, details=f'Fake refund for deposit: {payment.deposit_refund_transaction_id}')  # type: ignore

class NewCardDepositPaymentView(APIView):
    # permission_classes = [IsAuthenticated]  # مُعطل مؤقتاً للاختبار

    def post(self, request, rental_id):
        """
        يبدأ عملية دفع الديبوزيت بكارت جديد (يرجع رابط iframe فقط)
        """
        user = request.user
        amount_cents = request.data.get('amount_cents')
        payment_method = request.data.get('payment_method')
        payment_type = request.data.get('type', 'deposit')
        # تحقق من كل الفحوصات المطلوبة
        rental = get_object_or_404(SelfDriveRental, id=rental_id)
        
        # تأكد أن المالك أكد الحجز أولاً
        if rental.status != 'DepositRequired':
            return Response({'error_code': 'OWNER_CONFIRMATION_REQUIRED', 'error_message': 'يجب أن يؤكد مالك السيارة الحجز أولاً قبل دفع العربون.'}, status=400)
        
        if rental.renter != user:
            return Response({'error_code': 'NOT_RENTER', 'error_message': 'يجب أن تكون المستأجر في هذا الحجز.'}, status=403)
        payment = getattr(rental, 'payment', None)
        if not payment or not hasattr(payment, 'deposit_amount'):
            return Response({'error_code': 'PAYMENT_NOT_FOUND', 'error_message': 'لا يوجد بيانات دفع مرتبطة بهذا الحجز.'}, status=400)
        required_cents = int(round(float(payment.deposit_amount) * 100))
        if not amount_cents or int(amount_cents) != required_cents:
            return Response({'error_code': 'INVALID_AMOUNT', 'error_message': f'المبلغ المطلوب للعربون هو {required_cents} قرش.'}, status=400)
        if payment.deposit_paid_status == 'Paid':
            return Response({'error_code': 'ALREADY_PAID', 'error_message': 'تم دفع العربون بالفعل.'}, status=400)
        if payment_method != 'new_card':
            return Response({'error_code': 'INVALID_METHOD', 'error_message': 'طريقة الدفع يجب أن تكون new_card.'}, status=400)
        # تنفيذ منطق Paymob للبطاقات الجديدة
        try:
            auth_token = paymob.get_auth_token()
            import uuid
            reference = str(uuid.uuid4())
            user_id = str(user.id)
            # Use the new format that includes rental_id and rental_type for better tracking
            merchant_order_id_with_user = f"selfdrive_deposit_{rental_id}_{reference}_{user_id}"
            order_id = paymob.create_order(auth_token, amount_cents, merchant_order_id_with_user)
            integration_id = settings.PAYMOB_INTEGRATION_ID_CARD
            billing_data = {
                "apartment": "NA",
                "email": getattr(user, 'email', None) or "user@example.com",
                "floor": "NA",
                "first_name": getattr(user, 'first_name', None) or "Guest",
                "street": "NA",
                "building": "NA",
                "phone_number": getattr(user, 'phone_number', "01000000000"),
                "shipping_method": "NA",
                "postal_code": "NA",
                "city": "Cairo",
                "country": "EG",
                "last_name": getattr(user, 'last_name', None) or "User",
                "state": "EG"
            }
            payment_token = paymob.get_payment_token(
                auth_token, order_id, amount_cents, billing_data, integration_id
            )
            iframe_url = f"https://accept.paymob.com/api/acceptance/iframes/{settings.PAYMOB_IFRAME_ID}?payment_token={payment_token}"
            # يمكنك هنا حفظ order_id في payment أو جدول وسيط لو أردت تتبع العملية
            payment.deposit_transaction_id = order_id  # مؤقتًا لتتبع العملية
            payment.save()
            return Response({
                'iframe_url': iframe_url,
                'order_id': order_id,
                'message': 'يرجى إكمال الدفع عبر الرابط'
            })
        except Exception as e:
            return Response({'error_code': 'PAYMOB_ERROR', 'error_message': str(e)}, status=500)

    def get(self, request, rental_id):
        """
        يرجع حالة الدفع وتفاصيل آخر عملية (من SelfDrivePayment)
        """
        user = request.user
        rental = get_object_or_404(SelfDriveRental, id=rental_id)
        if rental.renter != user:
            return Response({'error_code': 'NOT_RENTER', 'error_message': 'يجب أن تكون المستأجر في هذا الحجز.'}, status=403)
        payment = getattr(rental, 'payment', None)
        if not payment:
            return Response({'error_code': 'PAYMENT_NOT_FOUND', 'error_message': 'لا يوجد بيانات دفع مرتبطة بهذا الحجز.'}, status=400)
        # يمكنك هنا إضافة تفاصيل أكثر من جدول الدفع أو من جدول منفصل لو حفظت تفاصيل Paymob
        from .serializers import SelfDrivePaymentSerializer
        return Response({
            'deposit_paid_status': payment.deposit_paid_status,
            'deposit_paid_at': payment.deposit_paid_at,
            'deposit_transaction_id': payment.deposit_transaction_id,
            'payment': SelfDrivePaymentSerializer(payment).data,
            # أضف هنا أي تفاصيل أخرى تحتاجها
        })


class PriceCalculatorView(APIView):
    """
    حساب السعر بدون حفظ في قاعدة البيانات
    POST /api/selfdrive-rentals/calculate-price/
    Body: {
        "car_id": 1,
        "start_date": "2025-07-05T10:00:00Z",
        "end_date": "2025-07-07T18:00:00Z"
    }
    """
    # permission_classes = [IsAuthenticated]  # مُعطل مؤقتاً للاختبار
    
    def post(self, request):
        from cars.models import Car
        
        car_id = request.data.get('car_id')
        start_date = request.data.get('start_date')
        end_date = request.data.get('end_date')
        
        if not all([car_id, start_date, end_date]):
            return Response({'error': 'car_id, start_date, and end_date are required'}, status=400)
            
        try:
            car = Car.objects.get(id=car_id)  # type: ignore
        except Car.DoesNotExist:  # type: ignore
            return Response({'error': 'Car not found'}, status=404)
            
        # Check if car has rental options and usage policy
        if not hasattr(car, 'rental_options') or not car.rental_options:
            return Response({'error': 'Car rental options not configured'}, status=400)
            
        if not hasattr(car, 'usage_policy') or not car.usage_policy:
            return Response({'error': 'Car usage policy not configured'}, status=400)
            
        options = car.rental_options
        policy = car.usage_policy
        
        if not options.daily_rental_price:
            return Response({'error': 'Daily rental price not set'}, status=400)
            
        # Parse dates
        from datetime import datetime
        try:
            start_dt = datetime.fromisoformat(start_date.replace('Z', '+00:00'))
            end_dt = datetime.fromisoformat(end_date.replace('Z', '+00:00'))
        except ValueError:
            return Response({'error': 'Invalid date format'}, status=400)
            
        # Calculate duration
        duration_days = (end_dt.date() - start_dt.date()).days + 1
        
        if duration_days <= 0:
            return Response({'error': 'Invalid date range'}, status=400)
            
        # Calculate financials
        financials = calculate_selfdrive_financials(options.daily_rental_price, duration_days)
        
        # Calculate allowed KM
        allowed_km = duration_days * float(policy.daily_km_limit)
        
        # Calculate payment breakdown
        total_cost = financials['final_cost']
        deposit_amount = round(total_cost * 0.15, 2)
        remaining_amount = round(total_cost - deposit_amount, 2)
        
        # Commission calculation
        commission_rate = 0.2
        platform_earnings = total_cost * commission_rate
        owner_earnings = total_cost - platform_earnings
        
        return Response({
            'car_info': {
                'id': car.id,
                'brand': car.brand,
                'model': car.model,
                'daily_price': float(options.daily_rental_price)
            },
            'rental_period': {
                'start_date': start_date,
                'end_date': end_date,
                'duration_days': duration_days
            },
            'pricing': {
                'base_cost': financials['base_cost'],
                'ctw_fee': financials['ctw_fee'],
                'total_cost': total_cost,
                'deposit_amount': deposit_amount,
                'remaining_amount': remaining_amount
            },
            'km_policy': {
                'daily_km_limit': float(policy.daily_km_limit),
                'total_allowed_km': allowed_km,
                'extra_km_cost': float(policy.extra_km_cost)
            },
            'earnings': {
                'commission_rate': commission_rate,
                'platform_earnings': platform_earnings,
                'owner_earnings': owner_earnings
            }
        })


class OwnerPendingPaymentsView(APIView):
    """
    عرض المدفوعات المعلقة للمالك (الزيادات المطلوب تحصيلها كاش)
    GET /api/selfdrive-rentals/owner/pending-payments/
    """
    # permission_classes = [IsAuthenticated]  # مُعطل مؤقتاً للاختبار
    
    def get(self, request):
        user = request.user
        
        # Get rentals where user is the car owner
        rentals = SelfDriveRental.objects.filter(car__owner=user).select_related(  # type: ignore
            'payment', 'breakdown', 'car'
        ).prefetch_related('car__owner')
        
        pending_payments = []
        
        for rental in rentals:
            payment = rental.payment
            breakdown = getattr(rental, 'breakdown', None)
            
            # Check for pending cash payments
            pending_items = []
            
            # Remaining amount (cash)
            if (payment.payment_method == 'cash' and 
                payment.remaining_paid_status == 'Pending'):
                pending_items.append({
                    'type': 'remaining_amount',
                    'amount': float(payment.remaining_amount),
                    'description': 'باقي مبلغ الإيجار (كاش)',
                    'due_stage': 'pickup'
                })
            
            # Excess amount (cash)
            if (payment.payment_method == 'cash' and 
                payment.excess_amount > 0 and 
                payment.excess_paid_status == 'Pending'):
                
                excess_details = []
                if breakdown:
                    if breakdown.extra_km_fee > 0:
                        excess_details.append(f"زيادة كيلومترات: {breakdown.extra_km} كم × {breakdown.extra_km_cost} = {breakdown.extra_km_fee} جنيه")
                    if breakdown.late_fee > 0:
                        excess_details.append(f"رسوم تأخير: {breakdown.late_days} يوم × {breakdown.daily_price * 1.3} = {breakdown.late_fee} جنيه")
                
                pending_items.append({
                    'type': 'excess_amount',
                    'amount': float(payment.excess_amount),
                    'description': 'رسوم إضافية (كاش)',
                    'details': excess_details,
                    'due_stage': 'return'
                })
            
            if pending_items:
                pending_payments.append({
                    'rental_id': rental.id,
                    'renter_name': rental.renter.get_full_name() or rental.renter.username,
                    'car_info': f"{rental.car.brand} {rental.car.model}",
                    'rental_status': rental.status,
                    'start_date': rental.start_date,
                    'end_date': rental.end_date,
                    'pending_items': pending_items,
                    'total_pending': sum(item['amount'] for item in pending_items)
                })
        
        return Response({
            'pending_payments': pending_payments,
            'total_rentals': len(pending_payments),
            'total_amount': sum(p['total_pending'] for p in pending_payments)
        })


class RentalStatusTimelineView(APIView):
    """
    عرض timeline مراحل الإيجار مع التفاصيل
    GET /api/selfdrive-rentals/{rental_id}/timeline/
    """
    # permission_classes = [IsAuthenticated]  # مُعطل مؤقتاً للاختبار
    
    def get(self, request, rental_id):
        try:
            rental = SelfDriveRental.objects.get(id=rental_id)  # type: ignore
        except SelfDriveRental.DoesNotExist:  # type: ignore
            return Response({'error': 'Rental not found'}, status=404)
            
            
        payment = rental.payment  # type: ignore
        contract = getattr(rental, 'contract', None)
        breakdown = getattr(rental, 'breakdown', None)
        
        # Build timeline
        timeline = []
        
        # 1. Rental Created
        timeline.append({
            'stage': 'created',
            'title': 'تم إنشاء الطلب',
            'status': 'completed',
            'timestamp': rental.created_at,
            'details': {
                'renter': rental.renter.get_full_name() or rental.renter.username,
                'car': f"{rental.car.brand} {rental.car.model}",
                'duration': f"{(rental.end_date.date() - rental.start_date.date()).days + 1} أيام"
            }
        })
        
        # 2. Owner Confirmation
        owner_confirmed = rental.status not in ['Pending', 'Canceled']
        timeline.append({
            'stage': 'owner_confirmation',
            'title': 'موافقة المالك',
            'status': 'completed' if owner_confirmed else 'pending',
            'timestamp': None,  # We don't track this timestamp
            'details': {
                'required': 'موافقة مالك السيارة على الطلب'
            }
        })
        
        # 3. Deposit Payment
        deposit_paid = payment.deposit_paid_status == 'Paid'
        timeline.append({
            'stage': 'deposit_payment',
            'title': 'دفع العربون',
            'status': 'completed' if deposit_paid else 'pending',
            'timestamp': payment.deposit_paid_at,
            'details': {
                'amount': float(payment.deposit_amount),
                'method': payment.payment_method,
                'transaction_id': payment.deposit_transaction_id
            }
        })
        
        # 4. Contract Signing
        if contract:
            both_signed = contract.renter_signed and contract.owner_signed
            timeline.append({
                'stage': 'contract_signing',
                'title': 'توقيع العقد',
                'status': 'completed' if both_signed else 'pending',
                'timestamp': contract.owner_signed_at if both_signed else None,
                'details': {
                    'renter_signed': contract.renter_signed,
                    'owner_signed': contract.owner_signed,
                    'renter_signed_at': contract.renter_signed_at,
                    'owner_signed_at': contract.owner_signed_at
                }
            })
        
        # 5. Pickup Handover
        if contract:
            pickup_done = contract.renter_pickup_done and contract.owner_pickup_done
            timeline.append({
                'stage': 'pickup_handover',
                'title': 'تسليم السيارة',
                'status': 'completed' if pickup_done else 'pending',
                'timestamp': contract.owner_pickup_done_at if pickup_done else None,
                'details': {
                    'renter_pickup_done': contract.renter_pickup_done,
                    'owner_pickup_done': contract.owner_pickup_done,
                    'remaining_payment_status': payment.remaining_paid_status
                }
            })
        
        # 6. Trip Started
        trip_started = rental.status in ['Ongoing', 'Finished']
        timeline.append({
            'stage': 'trip_started',
            'title': 'بدء الرحلة',
            'status': 'completed' if trip_started else 'pending',
            'timestamp': None,  # We could track this in logs
            'details': {
                'status': rental.status
            }
        })
        
        # 7. Return Handover
        if contract:
            return_done = contract.renter_return_done and contract.owner_return_done
            timeline.append({
                'stage': 'return_handover',
                'title': 'استلام السيارة',
                'status': 'completed' if return_done else 'pending',
                'timestamp': contract.owner_return_done_at if return_done else None,
                'details': {
                    'renter_return_done': contract.renter_return_done,
                    'owner_return_done': contract.owner_return_done,
                    'excess_amount': float(payment.excess_amount) if payment.excess_amount else 0
                }
            })
        
        # 8. Trip Finished
        trip_finished = rental.status == 'Finished'
        timeline.append({
            'stage': 'trip_finished',
            'title': 'انتهاء الرحلة',
            'status': 'completed' if trip_finished else 'pending',
            'timestamp': None,
            'details': {
                'final_cost': float(breakdown.final_cost) if breakdown else 0,
                'excess_paid': payment.excess_paid_status == 'Paid'
            }
        })
        
        return Response({
            'rental_id': rental.id,
            'current_status': rental.status,
            'timeline': timeline,
            'summary': {
                'total_cost': float(payment.rental_total_amount),
                'deposit_paid': deposit_paid,
                'remaining_status': payment.remaining_paid_status,
                'excess_amount': float(payment.excess_amount) if payment.excess_amount else 0
            }
        })


class RentalDashboardView(APIView):
    """
    Dashboard overview للمستخدم (رينتر أو أونر)
    GET /api/selfdrive-rentals/dashboard/
    """
    # permission_classes = [IsAuthenticated]  # مُعطل مؤقتاً للاختبار
    
    def get(self, request):
        user = request.user
        
        # Get rentals as renter
        as_renter = SelfDriveRental.objects.filter(renter=user).select_related(  # type: ignore
            'payment', 'car'
        ).order_by('-created_at')[:5]
        
        # Get rentals as owner
        as_owner = SelfDriveRental.objects.filter(car__owner=user).select_related(  # type: ignore
            'payment', 'car', 'renter'
        ).order_by('-created_at')[:5]
        
        def format_rental_summary(rental, role):
            payment = rental.payment
            return {
                'id': rental.id,
                'role': role,
                'status': rental.status,
                'car': f"{rental.car.brand} {rental.car.model}",
                'other_party': (rental.car.owner.get_full_name() or rental.car.owner.username) if role == 'renter' 
                              else (rental.renter.get_full_name() or rental.renter.username),
                'start_date': rental.start_date,
                'end_date': rental.end_date,
                'total_amount': float(payment.rental_total_amount),
                'needs_action': self._check_needs_action(rental, user)
            }
        
        renter_rentals = [format_rental_summary(r, 'renter') for r in as_renter]
        owner_rentals = [format_rental_summary(r, 'owner') for r in as_owner]
        
        # Statistics
        renter_stats = {
            'total_rentals': as_renter.count(),
            'active_rentals': as_renter.filter(status__in=['Confirmed', 'Ongoing']).count(),
            'pending_payments': as_renter.filter(payment__deposit_paid_status='Pending').count()
        }
        
        owner_stats = {
            'total_rentals': as_owner.count(),
            'pending_confirmations': as_owner.filter(status='PendingOwnerConfirmation').count(),
            'active_rentals': as_owner.filter(status__in=['Confirmed', 'Ongoing']).count()
        }
        
        return Response({
            'as_renter': {
                'rentals': renter_rentals,
                'stats': renter_stats
            },
            'as_owner': {
                'rentals': owner_rentals,
                'stats': owner_stats
            }
        })
    
    def _check_needs_action(self, rental, user):
        """Check if rental needs action from current user"""
        payment = rental.payment
        contract = getattr(rental, 'contract', None)
        
        if user == rental.renter:
            # Renter actions
            if payment.deposit_paid_status == 'Pending':
                return 'pay_deposit'
            if contract and not contract.renter_signed:
                return 'sign_contract'
            if contract and not contract.renter_pickup_done and rental.status == 'Confirmed':
                return 'pickup_handover'
            if rental.status == 'Ongoing':
                return 'trip_ongoing'
        
        elif user == rental.car.owner:
            # Owner actions
            if rental.status == 'PendingOwnerConfirmation':
                return 'confirm_rental'
            if contract and not contract.owner_signed:
                return 'sign_contract'
            if contract and not contract.owner_pickup_done and rental.status == 'Confirmed':
                return 'pickup_handover'
            if payment.payment_method == 'cash' and payment.remaining_paid_status == 'Pending':
                return 'confirm_cash_payment'
        
        return None


class CalculateExcessView(APIView):
    """
    حساب الزيادات بدون حفظ في قاعدة البيانات (للمعاينة)
    POST /api/selfdrive-rentals/{rental_id}/calculate-excess/
    Body: {
        "end_odometer_value": 15000,
        "actual_dropoff_time": "2025-07-07T20:00:00Z"  # optional, defaults to now
    }
    """
    # permission_classes = [IsAuthenticated]  # مُعطل مؤقتاً للاختبار
    
    def post(self, request, rental_id):
        try:
            rental = SelfDriveRental.objects.get(id=rental_id)  # type: ignore
        except SelfDriveRental.DoesNotExist:  # type: ignore
            return Response({'error': 'Rental not found'}, status=404)
            
        # Debug permission check (معطل مؤقتاً)
        print(f"=== DEBUG: Calculate Excess - Authentication DISABLED ===")
        print(f"Rental ID: {rental.id}")
        print(f"Rental Renter: {rental.renter.id} ({rental.renter.email})")
        print(f"Car Owner: {rental.car.owner.id} ({rental.car.owner.email})")
        print("Authentication check: SKIPPED")
        
        # Check permission - DISABLED for testing
        # if request.user not in [rental.renter, rental.car.owner] and not request.user.is_staff:
        #     return Response({
        #         'error': 'Permission denied',
        #         'debug_info': {
        #             'current_user_id': request.user.id,
        #             'renter_id': rental.renter.id,
        #             'owner_id': rental.car.owner.id,
        #             'is_staff': request.user.is_staff,
        #             'message': 'You must be either the renter, car owner, or staff member to access this rental'
        #         }
        #     }, status=403)
            
        end_odometer_value = request.data.get('end_odometer_value')
        actual_dropoff_time_str = request.data.get('actual_dropoff_time')
        
        if not end_odometer_value:
            return Response({'error': 'end_odometer_value is required'}, status=400)
            
        # Parse actual dropoff time
        if actual_dropoff_time_str:
            try:
                from datetime import datetime
                actual_dropoff_time = datetime.fromisoformat(actual_dropoff_time_str.replace('Z', '+00:00'))
            except ValueError:
                return Response({'error': 'Invalid actual_dropoff_time format'}, status=400)
        else:
            actual_dropoff_time = timezone.now()
            
        # Get existing breakdown or create temporary one
        breakdown = getattr(rental, 'breakdown', None)  # type: ignore
        if not breakdown:
            return Response({'error': 'Rental breakdown not found'}, status=404)
            
        # Get start odometer
        start_odometer_image = rental.odometer_images.filter(type='start').first()
        if not start_odometer_image:
            return Response({'error': 'Start odometer not found'}, status=400)
            
        start_odometer_value = start_odometer_image.value
        
        # Calculate KM excess
        actual_km = float(end_odometer_value) - start_odometer_value
        allowed_km = breakdown.allowed_km
        extra_km = max(0, actual_km - allowed_km)
        extra_km_cost = float(breakdown.extra_km_cost)
        extra_km_fee = extra_km * extra_km_cost
        
        # Calculate time excess (late return)
        planned_end_time = rental.end_date
        if actual_dropoff_time > planned_end_time:
            late_duration = actual_dropoff_time - planned_end_time
            late_days = max(1, late_duration.days + (1 if late_duration.seconds > 0 else 0))
            # Late fee is 30% extra per day
            late_fee_per_day = breakdown.daily_price * 1.3
            late_fee = late_days * late_fee_per_day
        else:
            late_days = 0
            late_fee = 0
            late_fee_per_day = 0
            
        # Calculate totals
        total_excess = extra_km_fee + late_fee
        final_cost = breakdown.initial_cost + total_excess
        
        # Commission calculation
        commission_rate = breakdown.commission_rate
        platform_earnings = final_cost * commission_rate
        driver_earnings = final_cost - platform_earnings
        
        return Response({
            'rental_id': rental.id,
            'calculation_time': actual_dropoff_time,
            'km_details': {
                'start_odometer': start_odometer_value,
                'end_odometer': float(end_odometer_value),
                'actual_km': actual_km,
                'allowed_km': allowed_km,
                'extra_km': extra_km,
                'extra_km_cost': extra_km_cost,
                'extra_km_fee': extra_km_fee
            },
            'time_details': {
                'planned_end_time': planned_end_time,
                'actual_dropoff_time': actual_dropoff_time,
                'late_days': late_days,
                'late_fee_per_day': late_fee_per_day,
                'late_fee': late_fee
            },
            'cost_summary': {
                'initial_cost': breakdown.initial_cost,
                'extra_km_fee': extra_km_fee,
                'late_fee': late_fee,
                'total_excess': total_excess,
                'final_cost': final_cost
            },
            'earnings': {
                'commission_rate': commission_rate,
                'platform_earnings': platform_earnings,
                'driver_earnings': driver_earnings
            },
            'payment_info': {
                'payment_method': rental.payment.payment_method,
                'will_auto_charge': rental.payment.payment_method in ['visa', 'wallet'],
                'requires_cash_collection': rental.payment.payment_method == 'cash' and total_excess > 0
            }
        })


class RenterDropoffPreviewView(APIView):
    """
    معاينة تفاصيل الـ drop off للمستأجر (قبل التأكيد)
    GET /api/selfdrive-rentals/{rental_id}/renter-dropoff-preview/
    """
    # permission_classes = [IsAuthenticated]  # مُعطل مؤقتاً للاختبار
    
    def get(self, request, rental_id):
        try:
            rental = SelfDriveRental.objects.get(id=rental_id)  # type: ignore
        except SelfDriveRental.DoesNotExist:  # type: ignore
            return Response({'error': 'Rental not found'}, status=404)
            
        # Check permission - only renter (معطل مؤقتاً للاختبار)
        # if request.user != rental.renter:
        #     return Response({'error': 'Only renter can access this'}, status=403)
            
        # Check rental status (معطل مؤقتاً للاختبار)
        # if rental.status != 'Ongoing':
        #     return Response({'error': 'Rental is not ongoing'}, status=400)
            
        payment = rental.payment  # type: ignore
        breakdown = getattr(rental, 'breakdown', None)  # type: ignore
        contract = getattr(rental, 'contract', None)  # type: ignore
        
        # Check if already done
        if contract and contract.renter_return_done:
            return Response({'error': 'Renter dropoff already completed'}, status=400)
            
        # Get start odometer for reference
        start_odometer_image = rental.odometer_images.filter(type='start').first()
        start_odometer_value = start_odometer_image.value if start_odometer_image else 0
        
        # Check if there's existing excess calculation
        existing_excess = 0
        if payment.excess_amount:
            existing_excess = float(payment.excess_amount)
            
        return Response({
            'rental_info': {
                'id': rental.id,
                'car': f"{rental.car.brand} {rental.car.model}",
                'owner_name': rental.car.owner.get_full_name() or rental.car.owner.username,
                'planned_end_time': rental.end_date,
                'current_time': timezone.now()
            },
            'odometer_info': {
                'start_value': start_odometer_value,
                'allowed_km': breakdown.allowed_km if breakdown else 0,
                'extra_km_cost': float(breakdown.extra_km_cost) if breakdown else 0
            },
            'payment_info': {
                'method': payment.payment_method,
                'initial_cost': breakdown.initial_cost if breakdown else 0,
                'existing_excess': existing_excess,
                'auto_charge_excess': payment.payment_method in ['visa', 'wallet']
            },
            'required_steps': [
                'Upload current car image',
                'Upload odometer image and enter current value',
                'Add any notes about car condition',
                'Confirm handover'
            ],
            'warnings': {
                'late_return': timezone.now() > rental.end_date,
                'auto_charge': payment.payment_method in ['visa', 'wallet']
            }
        })


class OwnerDropoffPreviewView(APIView):
    """
    معاينة تفاصيل الـ drop off للمالك (بعد تسليم المستأجر)
    GET /api/selfdrive-rentals/{rental_id}/owner-dropoff-preview/
    """
    # permission_classes = [IsAuthenticated]  # مُعطل مؤقتاً للاختبار
    
    def get(self, request, rental_id):
        try:
            rental = SelfDriveRental.objects.get(id=rental_id)  # type: ignore
        except SelfDriveRental.DoesNotExist:  # type: ignore
            return Response({'error': 'Rental not found'}, status=404)
            
        # Check permission - only owner (معطل مؤقتاً للاختبار)
        # if request.user != rental.car.owner:
        #     return Response({'error': 'Only owner can access this'}, status=403)
            
        payment = rental.payment  # type: ignore
        breakdown = getattr(rental, 'breakdown', None)  # type: ignore
        contract = getattr(rental, 'contract', None)  # type: ignore
        
        # Check if renter dropoff is done
        if not (contract and contract.renter_return_done):
            return Response({'error': 'Renter must complete dropoff first'}, status=400)
            
        # Check if already done
        if contract.owner_return_done:
            return Response({'error': 'Owner dropoff already completed'}, status=400)
            
        # Get excess details
        excess_amount = float(payment.excess_amount) if payment.excess_amount else 0
        
        # Build excess breakdown
        excess_details = []
        if breakdown:
            if breakdown.extra_km_fee > 0:
                excess_details.append({
                    'type': 'extra_km',
                    'description': f'زيادة كيلومترات: {breakdown.extra_km} كم',
                    'calculation': f'{breakdown.extra_km} × {breakdown.extra_km_cost} = {breakdown.extra_km_fee} جنيه',
                    'amount': float(breakdown.extra_km_fee)
                })
                
            if breakdown.late_fee > 0:
                excess_details.append({
                    'type': 'late_fee',
                    'description': f'رسوم تأخير: {breakdown.late_days} يوم',
                    'calculation': f'{breakdown.late_days} × {breakdown.daily_price * 1.3} = {breakdown.late_fee} جنيه',
                    'amount': float(breakdown.late_fee)
                })
        
        # Determine what owner needs to do
        cash_collection_required = (payment.payment_method == 'cash' and excess_amount > 0)
        
        return Response({
            'rental_info': {
                'id': rental.id,
                'car': f"{rental.car.brand} {rental.car.model}",
                'renter_name': rental.renter.get_full_name() or rental.renter.username,
                'renter_return_time': contract.renter_return_done_at
            },
            'excess_summary': {
                'total_amount': excess_amount,
                'details': excess_details,
                'payment_method': payment.payment_method,
                'already_charged': payment.payment_method in ['visa', 'wallet'] and payment.excess_paid_status == 'Paid'
            },
            'cash_collection': {
                'required': cash_collection_required,
                'amount_to_collect': excess_amount if cash_collection_required else 0,
                'status': payment.excess_paid_status if cash_collection_required else 'not_required'
            },
            'earnings_summary': {
                'final_cost': float(breakdown.final_cost) if breakdown else 0,
                'platform_commission': float(breakdown.platform_earnings) if breakdown else 0,
                'owner_earnings': float(breakdown.driver_earnings) if breakdown else 0
            },
            'required_steps': [
                'Review excess charges' if excess_amount > 0 else 'No excess charges',
                'Collect cash payment' if cash_collection_required else 'Payment already processed',
                'Add any notes about car condition',
                'Confirm handover completion'
            ],
            'uploaded_images': {
                'car_images': rental.car_images.filter(type='return', uploaded_by='renter').count(),
                'odometer_images': rental.odometer_images.filter(type='end').count()
            }
        })


class RentalSummaryView(APIView):
    """
    ملخص شامل للإيجار بعد الانتهاء
    GET /api/selfdrive-rentals/{rental_id}/summary/
    """
    # permission_classes = [IsAuthenticated]  # مُعطل مؤقتاً للاختبار
    
    def get(self, request, rental_id):
        try:
            rental = SelfDriveRental.objects.get(id=rental_id)  # type: ignore
        except SelfDriveRental.DoesNotExist:  # type: ignore
            return Response({'error': 'Rental not found'}, status=404)
            
        # Check permission (معطل مؤقتاً للاختبار)
        # if request.user not in [rental.renter, rental.car.owner]:
        #     return Response({'error': 'Permission denied'}, status=403)
            
        payment = rental.payment  # type: ignore
        breakdown = getattr(rental, 'breakdown', None)  # type: ignore
        contract = getattr(rental, 'contract', None)  # type: ignore
        
        # Get odometer readings
        start_odometer = rental.odometer_images.filter(type='start').first()
        end_odometer = rental.odometer_images.filter(type='end').first()
        
        # Build comprehensive summary
        summary = {
            'rental_info': {
                'id': rental.id,
                'status': rental.status,
                'car': f"{rental.car.brand} {rental.car.model}",
                'renter': rental.renter.get_full_name() or rental.renter.username,
                'owner': rental.car.owner.get_full_name() or rental.car.owner.username,
                'planned_period': {
                    'start': rental.start_date,
                    'end': rental.end_date,
                    'duration_days': (rental.end_date.date() - rental.start_date.date()).days + 1
                }
            },
            'actual_usage': {
                'actual_dropoff_time': breakdown.actual_dropoff_time if breakdown else None,
                'odometer': {
                    'start': float(start_odometer.value) if start_odometer else 0,
                    'end': float(end_odometer.value) if end_odometer else 0,
                    'total_km': float(end_odometer.value - start_odometer.value) if (start_odometer and end_odometer) else 0
                }
            },
            'cost_breakdown': {
                'initial_cost': float(breakdown.initial_cost) if breakdown else 0,
                'base_cost': float(breakdown.base_cost) if breakdown else 0,
                'ctw_fee': float(breakdown.ctw_fee) if breakdown else 0,
                'extra_charges': {
                    'extra_km_fee': float(breakdown.extra_km_fee) if breakdown else 0,
                    'late_fee': float(breakdown.late_fee) if breakdown else 0,
                    'total_extras': float(breakdown.total_extras_cost) if breakdown else 0
                },
                'final_cost': float(breakdown.final_cost) if breakdown else 0
            },
            'payment_details': {
                'method': payment.payment_method,
                'deposit': {
                    'amount': float(payment.deposit_amount),
                    'status': payment.deposit_paid_status,
                    'paid_at': payment.deposit_paid_at
                },
                'remaining': {
                    'amount': float(payment.remaining_amount),
                    'status': payment.remaining_paid_status,
                    'paid_at': payment.remaining_paid_at
                },
                'excess': {
                    'amount': float(payment.excess_amount) if payment.excess_amount else 0,
                    'status': payment.excess_paid_status,
                    'paid_at': payment.excess_paid_at
                }
            },
            'earnings': {
                'commission_rate': float(breakdown.commission_rate) if breakdown else 0,
                'platform_earnings': float(breakdown.platform_earnings) if breakdown else 0,
                'owner_earnings': float(breakdown.driver_earnings) if breakdown else 0
            },
            'timeline': {
                'created_at': rental.created_at,
                'pickup_completed': contract.owner_pickup_done_at if contract else None,
                'return_completed': contract.owner_return_done_at if contract else None
            },
            'user_role': 'renter' if request.user == rental.renter else 'owner'
        }
        
        return Response(summary)


class RentalPreviewView(APIView):
    """Preview rental details before creation"""
    permission_classes = [IsAuthenticated]
    
    def post(self, request):
        try:
            # Get data from request
            car_id = request.data.get('car')
            start_date = request.data.get('start_date')
            end_date = request.data.get('end_date')
            pickup_latitude = request.data.get('pickup_latitude')
            pickup_longitude = request.data.get('pickup_longitude')
            pickup_address = request.data.get('pickup_address')
            dropoff_latitude = request.data.get('dropoff_latitude')
            dropoff_longitude = request.data.get('dropoff_longitude')
            dropoff_address = request.data.get('dropoff_address')
            payment_method = request.data.get('payment_method', 'cash')
            selected_card = request.data.get('selected_card')
            
            # Validate required fields
            if not all([car_id, start_date, end_date, pickup_address, dropoff_address]):
                return Response({
                    'error': 'Missing required fields: car, start_date, end_date, pickup_address, dropoff_address'
                }, status=400)
            
            # Get car and validate
            from cars.models import Car
            try:
                car = Car.objects.get(id=car_id)  # type: ignore
            except Car.DoesNotExist:  # type: ignore
                return Response({'error': 'Car not found'}, status=404)  # type: ignore
            
            # Check if car is available
            # if not car.approval_status:
            #     return Response({'error': 'Car is not approved for rental'}, status=400)
            
            # Parse dates
            from datetime import datetime
            start_date_obj = datetime.strptime(start_date, '%Y-%m-%d').date()
            end_date_obj = datetime.strptime(end_date, '%Y-%m-%d').date()
            
            # Calculate duration
            duration_days = (end_date_obj - start_date_obj).days + 1
            
            # Get rental options and usage policy
            try:
                rental_options = car.rental_options
                usage_policy = car.usage_policy
            except Exception:
                return Response({'error': 'Car rental options or usage policy not configured'}, status=400)
            
            # Calculate financials
            daily_price = float(rental_options.daily_rental_price) if rental_options.daily_rental_price else 0
            if daily_price == 0:
                return Response({'error': 'Daily rental price not set for this car'}, status=400)
            
            # Calculate costs
            base_cost = daily_price * duration_days
            ctw_fee = base_cost * 0.15  # 15% service fee
            total_cost = base_cost + ctw_fee
            
            # Calculate deposit and remaining
            deposit_amount = round(total_cost * 0.15, 2)  # 15% deposit
            remaining_amount = round(total_cost - deposit_amount, 2)
            
            # Get allowed kilometers
            daily_km_limit = float(usage_policy.daily_km_limit) if usage_policy.daily_km_limit else 0
            total_allowed_km = daily_km_limit * duration_days
            extra_km_cost = float(usage_policy.extra_km_cost) if usage_policy.extra_km_cost else 0
            
            # Get car owner info
            owner_name = f"{car.owner.first_name} {car.owner.last_name}".strip() or car.owner.email
            
            # Get car images from documents
            from documents.models import Document
            car_images = []
            try:
                car_documents = Document.objects.filter(car=car)  # type: ignore
                print(f"Found {car_documents.count()} documents for car {car.id}")
                for doc in car_documents:
                    print(f"Document {doc.id}: file={doc.file}, name={doc.file.name if doc.file else 'None'}")
                    if hasattr(doc, 'file') and doc.file and doc.file.name:
                        try:
                            # تأكد من أن الملف موجود فعلاً وأنه ليس مجلد
                            if doc.file.storage.exists(doc.file.name) and not doc.file.name.endswith('/'):
                                # تأكد من أن الـ URL صحيح
                                if doc.file.url and not doc.file.url.endswith('/'):
                                    image_url = request.build_absolute_uri(doc.file.url) if request else doc.file.url
                                    car_images.append({
                                        'id': doc.id,
                                        'url': image_url,
                                        'type': doc.document_type.name if doc.document_type else 'Unknown',
                                        'filename': doc.file.name
                                    })
                                else:
                                    print(f"Invalid URL for document {doc.id}: {doc.file.url}")
                            else:
                                print(f"File not found or is directory: {doc.file.name}")
                        except Exception as img_error:
                            print(f"Error processing image {doc.id}: {str(img_error)}")
                            continue
            except Exception as e:
                print(f"Error getting car images: {str(e)}")
                car_images = []  # Return empty list if error
            
            # Build response
            response_data = {
                'car_details': {
                    'id': car.id,
                    'brand': car.brand,
                    'model': car.model,
                    'year': car.year,
                    'color': car.color,
                    'plate_number': car.plate_number,
                    'transmission_type': car.transmission_type,
                    'fuel_type': car.fuel_type,
                    'seating_capacity': car.seating_capacity,
                    'avg_rating': float(car.avg_rating),
                    'total_reviews': car.total_reviews,
                    'owner_name': owner_name,
                    'owner_rating': float(car.owner.avg_rating) if hasattr(car.owner, 'avg_rating') else 0,
                    'images': car_images,
                },
                'rental_details': {
                    'start_date': start_date,
                    'end_date': end_date,
                    'duration_days': duration_days,
                    'pickup_address': pickup_address,
                    'dropoff_address': dropoff_address,
                    'pickup_latitude': pickup_latitude,
                    'pickup_longitude': pickup_longitude,
                    'dropoff_latitude': dropoff_latitude,
                    'dropoff_longitude': dropoff_longitude,
                },
                'pricing': {
                    'daily_price': daily_price,
                    'base_cost': base_cost,
                    'service_fee': ctw_fee,
                    'service_fee_percentage': 15,
                    'total_cost': total_cost,
                    'deposit_amount': deposit_amount,
                    'remaining_amount': remaining_amount,
                    'deposit_percentage': 15,
                },
                'usage_policy': {
                    'daily_km_limit': daily_km_limit,
                    'total_allowed_km': total_allowed_km,
                    'extra_km_cost': extra_km_cost,
                    'daily_hour_limit': usage_policy.daily_hour_limit,
                    'extra_hour_cost': float(usage_policy.extra_hour_cost) if usage_policy.extra_hour_cost else 0,
                },
                'payment_methods': {
                    'selected_method': payment_method,
                    'selected_card_id': selected_card,
                    'available_methods': ['visa', 'wallet', 'cash']
                },
                'platform_policies': {
                    'cancellation_policy': f'No free cancellation. Deposit will be forfeited if cancelled after payment',
                    'insurance_policy': 'Full liability insurance up to 40,000 EGP for car repairs',
                    'fuel_policy': 'Return with same fuel level as pickup. Fuel difference: 15 EGP/liter',
                    'late_return_policy': f'Late return fee: {daily_price:.0f} EGP per day (full day only)',
                    'damage_policy': f'Report any damage immediately. Rental deposit: {deposit_amount:.0f} EGP',
                    'km_policy': f'Daily limit: {daily_km_limit:.0f} km. Extra: {extra_km_cost:.0f} EGP/km',
                    'hour_policy': f'Daily limit: {usage_policy.daily_hour_limit or 24} hours. Extra: {float(usage_policy.extra_hour_cost) if usage_policy.extra_hour_cost else 0:.0f} EGP/hour',
                    'deposit_info': f'Rental deposit: {deposit_amount:.0f} EGP',
                }
            }
            
            return Response(response_data)
            
        except Exception as e:
            return Response({'error': str(e)}, status=500)
