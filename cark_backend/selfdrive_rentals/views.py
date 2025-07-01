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

import random


class SelfDriveRentalViewSet(viewsets.ModelViewSet):
    queryset = SelfDriveRental.objects.all()
    serializer_class = SelfDriveRentalSerializer

    def perform_create(self, serializer):
        with transaction.atomic():
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
            SelfDriveRentalBreakdown.objects.create(
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
            SelfDrivePayment.objects.create(
                rental=rental,
                deposit_amount=deposit_amount,
                deposit_paid_status='Pending',
                remaining_amount=remaining_amount,
                remaining_paid_status='Pending',
                payment_method=payment_method,
                rental_total_amount=initial_cost
            )
            SelfDriveContract.objects.create(rental=rental)

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
                from .serializers import SelfDrivePaymentSerializer
                return Response({
                    'status': 'deposit payment processed successfully.',
                    'transaction_id': result['transaction_id'],
                    'payment': SelfDrivePaymentSerializer(payment).data,
                    'paymob_details': result
                })
            except Exception as e:
                return Response({'error_code': 'PAYMENT_ERROR', 'error_message': str(e)}, status=500)

        # ... باقي الكود القديم ...

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
        return Response({'status': 'تم تأكيد الحجز من المالك. يجب دفع العربون خلال 24 ساعة.'})

    @action(detail=True, methods=['post'])
    def deposit_paid(self, request, pk=None):
        rental = self.get_object()
        payment = rental.payment
        if payment.deposit_paid_status == 'Paid':
            return Response({'error_code': 'ALREADY_PAID', 'error_message': 'تم دفع العربون بالفعل.'}, status=400)
        payment.deposit_paid_status = 'Paid'
        payment.deposit_paid_at = timezone.now()
        payment.save()
        # توليد العقد PDF بعد دفع العربون
        contract = rental.contract
        contract_pdf_bytes = generate_contract_pdf(rental)
        contract.contract_pdf.save(f'contract_rental_{rental.id}.pdf', ContentFile(contract_pdf_bytes))
        contract.save()
        SelfDriveRentalLog.objects.create(rental=rental, action='deposit_paid', user=request.user, details='Renter paid the deposit. Contract generated.')
        return Response({'status': 'تم دفع العربون وتم توليد العقد.'})

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
        return Response({
            'status': 'تم استلام السيارة من المستأجر.',
            'renter_signed': contract.renter_signed,
            'car_image': car_image.name,
            'odometer_image': odometer_image.name,
            'remaining_paid_status': payment.remaining_paid_status,
            'paymob_details': paymob_details
        })

    @action(detail=True, methods=['post'])
    def renter_return_handover(self, request, pk=None):
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
            return Response({'error_code': 'CAR_IMAGE_REQUIRED', 'error_message': 'صورة العربية مطلوبة.'}, status=400)
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
        # لا يمكن تنفيذ هاند أوفر المالك إلا بعد هاند أوفر المستأجر
        if not contract.renter_return_done:
            return Response({'error_code': 'RENTER_HANDOVER_REQUIRED', 'error_message': 'يجب أن يقوم المستأجر بتسليم السيارة أولاً.'}, status=400)
        if contract.owner_return_done:
            return Response({'error_code': 'OWNER_RETURN_HANDOVER_ALREADY_DONE', 'error_message': 'تم تنفيذ تسليم المالك (نهاية الرحلة) بالفعل ولا يمكن تكراره.'}, status=400)
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
    SelfDriveRentalBreakdown.objects.update_or_create(
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
    payment, _ = SelfDrivePayment.objects.get_or_create(rental=rental)
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
        SelfDriveRentalLog.objects.create(rental=payment.rental, action='payment', user=user, details=f'Fake payment for remaining: {transaction_id}')
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
        SelfDriveRentalLog.objects.create(rental=payment.rental, action='payment', user=user, details=f'Fake payment for excess: {transaction_id}')
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
    SelfDriveRentalLog.objects.create(rental=payment.rental, action='deposit_refund', user=user, details=f'Fake refund for deposit: {payment.deposit_refund_transaction_id}')

class NewCardDepositPaymentView(APIView):
    permission_classes = [IsAuthenticated]

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
            merchant_order_id_with_user = f"{reference}_{user_id}"
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
