from rest_framework import viewsets , status, filters
from rest_framework.permissions import IsAuthenticated
from .models import Car, CarRentalOptions, CarUsagePolicy, CarStats, CarUsagePolicy
from .serializers import CarSerializer, CarRentalOptionsSerializer, CarUsagePolicySerializer, CarStatsSerializer , CarUsagePolicySerializer
from rest_framework.response import Response
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework import status
from django.shortcuts import get_object_or_404
from django_filters.rest_framework import DjangoFilterBackend
from django.db import models
from rest_framework.views import APIView
from django.core.exceptions import ValidationError
import re

class CarViewSet(viewsets.ModelViewSet):
    queryset = Car.objects.all()
    serializer_class = CarSerializer
    #permission_classes = [IsAuthenticated]

    def perform_create(self, serializer):
         # أخذ المستخدم من التوكن المرسل مع الطلب
        user = self.request.user
        # إضافة المستخدم كـ owner عند إنشاء السيارة
        serializer.save(owner=user)


class CarRentalOptionsViewSet(viewsets.ModelViewSet):
    queryset = CarRentalOptions.objects.all()
    serializer_class = CarRentalOptionsSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter]
    filterset_fields = ['car', 'available_with_driver']

    def create(self, request, *args, **kwargs):
        car_id = request.data.get('car')
        if not car_id:
            return Response({'error': 'Car ID is required.'}, status=status.HTTP_400_BAD_REQUEST)

        car = get_object_or_404(Car, id=car_id)

        if car.owner != request.user:
            return Response({'error': 'You are not the owner of this car.'}, status=status.HTTP_403_FORBIDDEN)

        if hasattr(car, 'rental_options'):
            return Response({'error': 'Rental options already exist for this car.'}, status=status.HTTP_400_BAD_REQUEST)

        data = request.data.copy()
        prices = [
            data.get('daily_rental_price'),
            data.get('monthly_rental_price'),
            data.get('yearly_rental_price'),
            data.get('daily_rental_price_with_driver'),
            data.get('monthly_price_with_driver'),
            data.get('yearly_price_with_driver'),
        ]

        if all(price in [None, 0, '0', ''] for price in prices):
            return Response({'error': 'At least one rental price must be provided.'}, status=status.HTTP_400_BAD_REQUEST)

        return super().create(request, *args, **kwargs)

    def update(self, request, *args, **kwargs):
        instance = self.get_object()
        car = instance.car

        if car.owner != request.user:
            return Response({'error': 'You are not the owner of this car.'}, status=status.HTTP_403_FORBIDDEN)

        return super().update(request, *args, **kwargs)

    def partial_update(self, request, *args, **kwargs):
        instance = self.get_object()
        car = instance.car

        if car.owner != request.user:
            return Response({'error': 'You are not the owner of this car.'}, status=status.HTTP_403_FORBIDDEN)

        return super().partial_update(request, *args, **kwargs)

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        car = instance.car

        if car.owner != request.user:
            return Response({'error': 'You are not the owner of this car.'}, status=status.HTTP_403_FORBIDDEN)

        return super().destroy(request, *args, **kwargs)




class CarUsagePolicyViewSet(viewsets.ModelViewSet):
    queryset = CarUsagePolicy.objects.all()
    serializer_class = CarUsagePolicySerializer
    permission_classes = [IsAuthenticated]

    # 1. عرض كل سياسات الاستخدام لكل العربيات
    def list(self, request, *args, **kwargs):
        queryset = CarUsagePolicy.objects.all()
        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)

    # 2. عرض سياسة الاستخدام لعربية معينة
    def retrieve(self, request, *args, **kwargs):
        car_usage_policy = self.get_object()
        serializer = self.get_serializer(car_usage_policy)
        return Response(serializer.data)

    # 3. إضافة سياسة استخدام جديدة لعربية
    def create(self, request, *args, **kwargs):
        car_id = request.data.get('car')
        if not car_id:
            return Response({'error': 'Car ID is required.'}, status=status.HTTP_400_BAD_REQUEST)

        car = get_object_or_404(Car, id=car_id)
        
        # تأكد ان المالك هو نفس المستخدم
        if car.owner != request.user:
            return Response({'error': 'You are not the owner of this car.'}, status=status.HTTP_403_FORBIDDEN)

        # تحقق إذا كانت سياسة الاستخدام موجودة بالفعل
        if hasattr(car, 'usage_policy'):
            return Response({'error': 'Usage policy already exists for this car.'}, status=status.HTTP_400_BAD_REQUEST)
        
        return super().create(request, *args, **kwargs)

    # 4. تعديل كل سياسة الاستخدام
    def update(self, request, *args, **kwargs):
        instance = self.get_object()
        car = instance.car

        # تحقق من الملكية
        if car.owner != request.user:
            return Response({'error': 'You are not the owner of this car.'}, status=status.HTTP_403_FORBIDDEN)

        return super().update(request, *args, **kwargs)

    # 5. تعديل جزئي لسياسة الاستخدام
    def partial_update(self, request, *args, **kwargs):
        instance = self.get_object()
        car = instance.car

        # تحقق من الملكية
        if car.owner != request.user:
            return Response({'error': 'You are not the owner of this car.'}, status=status.HTTP_403_FORBIDDEN)

        return super().partial_update(request, *args, **kwargs)
    

    

    # 6. حذف سياسة الاستخدام لعربية معينة
    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        car = instance.car

        # تحقق من الملكية
        if car.owner != request.user:
            return Response({'error': 'You are not the owner of this car.'}, status=status.HTTP_403_FORBIDDEN)

        return super().destroy(request, *args, **kwargs)


class CarStatsViewSet(viewsets.ModelViewSet):
    queryset = CarStats.objects.all()
    serializer_class = CarStatsSerializer
    #permission_classes = [IsAuthenticated]



class CarRentalOptionsViewSet(viewsets.ModelViewSet):
    queryset = CarRentalOptions.objects.all()
    serializer_class = CarRentalOptionsSerializer
    permission_classes = [IsAuthenticated]
    #filter_backends = [DjangoFilterBackend, filters.SearchFilter]
    #filterset_fields = ['car', 'available_with_driver']

    # Endpoint مخصص لتعديل rental options بناء على car id
    @action(detail=False, methods=['patch'], url_path='by-car/(?P<car_id>\d+)')
    def update_by_car(self, request, car_id=None):
        car = get_object_or_404(Car, id=car_id)
        
        # تأكد ان المالك هو نفس المستخدم
        if car.owner != request.user:
            return Response({'error': 'You are not the owner of this car.'}, status=status.HTTP_403_FORBIDDEN)

        # جلب rental option المرتبط بالعربية
        rental_option = get_object_or_404(CarRentalOptions, car=car)

        # استخدام الـ serializer للتعديل
        serializer = self.get_serializer(rental_option, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    

    
class CarUsagePolicyViewSet(viewsets.ModelViewSet):
    queryset = CarUsagePolicy.objects.all()
    serializer_class = CarUsagePolicySerializer
    permission_classes = [IsAuthenticated]

    @action(detail=False, methods=['patch'], url_path='by-car/(?P<car_id>[^/.]+)')
    def partial_update_by_car(self, request, car_id=None):
        try:
            usage_policy = CarUsagePolicy.objects.get(car__id=car_id)
        except CarUsagePolicy.DoesNotExist:
            return Response({'error': 'Usage policy for this car not found.'}, status=404)

        serializer = self.get_serializer(usage_policy, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)


class CarStatsViewSet(viewsets.ModelViewSet):
    queryset = CarStats.objects.all()
    serializer_class = CarStatsSerializer
    permission_classes = [IsAuthenticated]

    @action(detail=False, methods=['patch'], url_path='by-car/(?P<car_id>[^/.]+)')
    def patch_by_car(self, request, car_id=None):
        try:
            car_stats = CarStats.objects.get(car__id=car_id)
        except CarStats.DoesNotExist:
            return Response({'error': 'Car stats not found.'}, status=status.HTTP_404_NOT_FOUND)

        serializer = self.get_serializer(car_stats, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)
    
    @action(detail=False, methods=['get'], url_path='by-car/(?P<car_id>[^/.]+)')
    def get_by_car(self, request, car_id=None):
        try:
            car_stats = CarStats.objects.get(car__id=car_id)
        except CarStats.DoesNotExist:
            return Response({'error': 'No stats found for this car.'}, status=status.HTTP_404_NOT_FOUND)
        
        serializer = self.get_serializer(car_stats)
        return Response(serializer.data)

    @action(detail=False, methods=['get'], url_path='summary')
    def get_summary(self, request):
        total_rentals = CarStats.objects.aggregate(total=models.Sum('rental_history_count'))
        total_earned = CarStats.objects.aggregate(total=models.Sum('total_earned'))
        return Response({
            'total_rentals': total_rentals['total'] or 0,
            'total_earned': total_earned['total'] or 0
        })

class MyCarsView(APIView):
    permission_classes = [IsAuthenticated]
    def get(self, request):
        cars = Car.objects.filter(owner=request.user)
        serializer = CarSerializer(cars, many=True)
        return Response(serializer.data)

class CarValidationTestView(APIView):
    """
    تيست وتحقق من بيانات العربية بدون حفظ في قاعدة البيانات
    POST /api/cars/test-validation/
    """
    permission_classes = [IsAuthenticated]
    
    def post(self, request):
        stage = request.data.get('stage', 'basic_info')
        
        if stage == 'basic_info':
            return self._validate_basic_info(request.data)
        elif stage == 'rental_options':
            return self._validate_rental_options(request.data)
        elif stage == 'usage_policy':
            return self._validate_usage_policy(request.data)
        elif stage == 'complete':
            return self._validate_complete_car(request.data)
        else:
            return Response({'error': 'Invalid stage'}, status=400)
    
    def _validate_basic_info(self, data):
        """تحقق من البيانات الأساسية للعربية"""
        errors = {}
        warnings = []
        
        # التحقق من الحقول المطلوبة
        required_fields = ['model', 'brand', 'car_type', 'car_category', 'plate_number', 
                          'year', 'color', 'seating_capacity', 'transmission_type', 
                          'fuel_type', 'current_odometer_reading']
        
        for field in required_fields:
            if not data.get(field):
                errors[field] = f'{field} is required'
        
        # التحقق من رقم اللوحة
        plate_number = data.get('plate_number')
        if plate_number:
            # تحقق من تنسيق رقم اللوحة المصري
            if not re.match(r'^[أ-ي\s\d]+$', plate_number) and not re.match(r'^[A-Z\s\d]+$', plate_number):
                errors['plate_number'] = 'Invalid plate number format'
            
            # تحقق من عدم تكرار رقم اللوحة
            if Car.objects.filter(plate_number=plate_number).exists():  # type: ignore
                errors['plate_number'] = 'Plate number already exists'
        
        # التحقق من السنة
        year = data.get('year')
        if year:
            try:
                year = int(year)
                if year < 1990 or year > 2025:
                    errors['year'] = 'Year must be between 1990 and 2025'
                elif year < 2010:
                    warnings.append('Cars older than 2010 may have limited rental demand')
            except (ValueError, TypeError):
                errors['year'] = 'Invalid year format'
        
        # التحقق من عدد المقاعد
        seating_capacity = data.get('seating_capacity')
        if seating_capacity:
            try:
                capacity = int(seating_capacity)
                if capacity < 2 or capacity > 15:
                    errors['seating_capacity'] = 'Seating capacity must be between 2 and 15'
            except (ValueError, TypeError):
                errors['seating_capacity'] = 'Invalid seating capacity format'
        
        # التحقق من قراءة العداد
        odometer = data.get('current_odometer_reading')
        if odometer:
            try:
                odometer_val = int(odometer)
                if odometer_val < 0:
                    errors['current_odometer_reading'] = 'Odometer reading cannot be negative'
                elif odometer_val > 500000:
                    warnings.append('High odometer reading may affect rental attractiveness')
            except (ValueError, TypeError):
                errors['current_odometer_reading'] = 'Invalid odometer reading format'
        
        # التحقق من الخيارات المحددة
        valid_choices = {
            'car_type': [choice[0] for choice in Car.CAR_TYPE_CHOICES],
            'car_category': [choice[0] for choice in Car.CAR_CATEGORY_CHOICES],
            'transmission_type': [choice[0] for choice in Car.TRANSMISSION_CHOICES],
            'fuel_type': [choice[0] for choice in Car.FUEL_CHOICES]
        }
        
        for field, choices in valid_choices.items():
            value = data.get(field)
            if value and value not in choices:
                errors[field] = f'Invalid choice. Valid options: {", ".join(choices)}'
        
        return Response({
            'stage': 'basic_info',
            'valid': len(errors) == 0,
            'errors': errors,
            'warnings': warnings,
            'message': 'Basic info validation complete' if len(errors) == 0 else 'Please fix the errors above'
        })
    
    def _validate_rental_options(self, data):
        """تحقق من خيارات الإيجار"""
        errors = {}
        warnings = []
        
        # التحقق من توفر خيار واحد على الأقل
        without_driver = data.get('available_without_driver', False)
        with_driver = data.get('available_with_driver', False)
        
        if not without_driver and not with_driver:
            errors['availability'] = 'At least one rental option must be available'
        
        # التحقق من الأسعار بدون سائق
        if without_driver:
            daily_price = data.get('daily_rental_price')
            if not daily_price:
                errors['daily_rental_price'] = 'Daily price is required when available without driver'
            else:
                try:
                    price = float(daily_price)
                    if price <= 0:
                        errors['daily_rental_price'] = 'Price must be greater than 0'
                    elif price < 100:
                        warnings.append('Daily price seems low, consider market rates')
                    elif price > 2000:
                        warnings.append('Daily price seems high, may reduce bookings')
                except (ValueError, TypeError):
                    errors['daily_rental_price'] = 'Invalid price format'
            
            # أسعار اختيارية
            monthly_price = data.get('monthly_rental_price')
            if monthly_price:
                try:
                    monthly = float(monthly_price)
                    daily = float(daily_price) if daily_price else 0
                    if monthly > 0 and daily > 0:
                        expected_monthly = daily * 25  # خصم 5 أيام للشهر
                        if monthly > expected_monthly:
                            warnings.append(f'Monthly price seems high compared to daily rate. Suggested: {expected_monthly}')
                except (ValueError, TypeError):
                    errors['monthly_rental_price'] = 'Invalid monthly price format'
        
        # التحقق من الأسعار مع سائق
        if with_driver:
            daily_with_driver = data.get('daily_rental_price_with_driver')
            if not daily_with_driver:
                errors['daily_rental_price_with_driver'] = 'Daily price with driver is required'
            else:
                try:
                    price_with_driver = float(daily_with_driver)
                    if price_with_driver <= 0:
                        errors['daily_rental_price_with_driver'] = 'Price must be greater than 0'
                    
                    # مقارنة مع السعر بدون سائق
                    daily_without = data.get('daily_rental_price')
                    if daily_without:
                        try:
                            without_price = float(daily_without)
                            if price_with_driver <= without_price:
                                errors['daily_rental_price_with_driver'] = 'Price with driver should be higher than without driver'
                            elif price_with_driver < without_price * 1.5:
                                warnings.append('Price with driver might be too low compared to without driver')
                        except (ValueError, TypeError):
                            pass
                except (ValueError, TypeError):
                    errors['daily_rental_price_with_driver'] = 'Invalid price format'
        
        return Response({
            'stage': 'rental_options',
            'valid': len(errors) == 0,
            'errors': errors,
            'warnings': warnings,
            'message': 'Rental options validation complete' if len(errors) == 0 else 'Please fix the errors above'
        })
    
    def _validate_usage_policy(self, data):
        """تحقق من سياسة الاستخدام"""
        errors = {}
        warnings = []
        
        # التحقق من الحقول المطلوبة
        daily_km_limit = data.get('daily_km_limit')
        if not daily_km_limit:
            errors['daily_km_limit'] = 'Daily KM limit is required'
        else:
            try:
                km_limit = float(daily_km_limit)
                if km_limit <= 0:
                    errors['daily_km_limit'] = 'KM limit must be greater than 0'
                elif km_limit < 100:
                    warnings.append('Low daily KM limit may discourage renters')
                elif km_limit > 500:
                    warnings.append('High daily KM limit may increase costs')
            except (ValueError, TypeError):
                errors['daily_km_limit'] = 'Invalid KM limit format'
        
        extra_km_cost = data.get('extra_km_cost')
        if not extra_km_cost:
            errors['extra_km_cost'] = 'Extra KM cost is required'
        else:
            try:
                km_cost = float(extra_km_cost)
                if km_cost <= 0:
                    errors['extra_km_cost'] = 'Extra KM cost must be greater than 0'
                elif km_cost < 0.5:
                    warnings.append('Low extra KM cost may encourage overuse')
                elif km_cost > 5:
                    warnings.append('High extra KM cost may discourage rentals')
            except (ValueError, TypeError):
                errors['extra_km_cost'] = 'Invalid extra KM cost format'
        
        # التحقق من ساعات الاستخدام (اختياري)
        daily_hour_limit = data.get('daily_hour_limit')
        if daily_hour_limit:
            try:
                hour_limit = int(daily_hour_limit)
                if hour_limit <= 0:
                    errors['daily_hour_limit'] = 'Hour limit must be greater than 0'
                elif hour_limit > 24:
                    errors['daily_hour_limit'] = 'Hour limit cannot exceed 24 hours'
                elif hour_limit < 8:
                    warnings.append('Low daily hour limit may be restrictive')
                
                # التحقق من تكلفة الساعة الإضافية
                extra_hour_cost = data.get('extra_hour_cost')
                if not extra_hour_cost:
                    errors['extra_hour_cost'] = 'Extra hour cost is required when hour limit is set'
                else:
                    try:
                        hour_cost = float(extra_hour_cost)
                        if hour_cost <= 0:
                            errors['extra_hour_cost'] = 'Extra hour cost must be greater than 0'
                    except (ValueError, TypeError):
                        errors['extra_hour_cost'] = 'Invalid extra hour cost format'
            except (ValueError, TypeError):
                errors['daily_hour_limit'] = 'Invalid hour limit format'
        
        return Response({
            'stage': 'usage_policy',
            'valid': len(errors) == 0,
            'errors': errors,
            'warnings': warnings,
            'message': 'Usage policy validation complete' if len(errors) == 0 else 'Please fix the errors above'
        })
    
    def _validate_complete_car(self, data):
        """تحقق شامل من جميع بيانات العربية"""
        # تجميع جميع التحققات
        basic_validation = self._validate_basic_info(data)
        rental_validation = self._validate_rental_options(data)
        policy_validation = self._validate_usage_policy(data)
        
        all_errors = {}
        all_warnings = []
        
        # جمع الأخطاء والتحذيرات
        if basic_validation.data['errors']:
            all_errors.update(basic_validation.data['errors'])
        if rental_validation.data['errors']:
            all_errors.update(rental_validation.data['errors'])
        if policy_validation.data['errors']:
            all_errors.update(policy_validation.data['errors'])
        
        all_warnings.extend(basic_validation.data['warnings'])
        all_warnings.extend(rental_validation.data['warnings'])
        all_warnings.extend(policy_validation.data['warnings'])
        
        # تحققات إضافية للتكامل
        daily_price = data.get('daily_rental_price')
        km_limit = data.get('daily_km_limit')
        extra_km_cost = data.get('extra_km_cost')
        
        if daily_price and km_limit and extra_km_cost:
            try:
                price = float(daily_price)
                limit = float(km_limit)
                cost = float(extra_km_cost)
                
                # حساب التكلفة المتوقعة للكيلو الواحد
                cost_per_km = price / limit
                if extra_km_cost < cost_per_km * 0.5:
                    all_warnings.append('Extra KM cost is significantly lower than base cost per KM')
                elif extra_km_cost > cost_per_km * 3:
                    all_warnings.append('Extra KM cost is significantly higher than base cost per KM')
            except (ValueError, TypeError):
                pass
        
        is_valid = len(all_errors) == 0
        
        return Response({
            'stage': 'complete',
            'valid': is_valid,
            'errors': all_errors,
            'warnings': all_warnings,
            'summary': {
                'basic_info': basic_validation.data['valid'],
                'rental_options': rental_validation.data['valid'],
                'usage_policy': policy_validation.data['valid'],
                'ready_to_submit': is_valid
            },
            'message': 'Car data is ready for submission!' if is_valid else 'Please fix all errors before submitting'
        })


class PlateNumberCheckView(APIView):
    """
    تحقق من توفر رقم اللوحة
    POST /api/cars/check-plate/
    Body: {"plate_number": "ABC123"}
    """
    permission_classes = [IsAuthenticated]
    
    def post(self, request):
        plate_number = request.data.get('plate_number')
        
        if not plate_number:
            return Response({'error': 'plate_number is required'}, status=400)
        
        # تحقق من التنسيق
        is_valid_format = bool(re.match(r'^[أ-ي\s\d]+$', plate_number) or re.match(r'^[A-Z\s\d]+$', plate_number))
        
        # تحقق من التوفر
        is_available = not Car.objects.filter(plate_number=plate_number).exists()  # type: ignore
        
        return Response({
            'plate_number': plate_number,
            'valid_format': is_valid_format,
            'available': is_available,
            'message': 'Plate number is available' if (is_valid_format and is_available) else 
                      'Invalid format' if not is_valid_format else 'Plate number already exists'
        })


class PricingSuggestionView(APIView):
    """
    اقتراح أسعار بناءً على نوع العربية والسوق
    POST /api/cars/suggest-pricing/
    Body: {"car_type": "SUV", "car_category": "Luxury", "year": 2020}
    """
    permission_classes = [IsAuthenticated]
    
    def post(self, request):
        car_type = request.data.get('car_type')
        car_category = request.data.get('car_category')
        year = request.data.get('year')
        
        if not all([car_type, car_category, year]):
            return Response({'error': 'car_type, car_category, and year are required'}, status=400)
        
        try:
            year = int(year)
        except (ValueError, TypeError):
            return Response({'error': 'Invalid year format'}, status=400)
        
        # منطق اقتراح الأسعار (يمكن تطويره بناءً على بيانات السوق الفعلية)
        base_prices = {
            'Economy': {'SUV': 300, 'Sedan': 250, 'Hatchback': 200, 'Other': 220},
            'Luxury': {'SUV': 600, 'Sedan': 500, 'Hatchback': 400, 'Other': 450},
            'Sports': {'SUV': 800, 'Sedan': 700, 'Hatchback': 600, 'Other': 650},
            'Electric': {'SUV': 400, 'Sedan': 350, 'Hatchback': 300, 'Other': 320}
        }
        
        # السعر الأساسي
        base_price = base_prices.get(car_category, {}).get(car_type, 300)
        
        # تعديل السعر حسب السنة
        current_year = 2024
        age = current_year - year
        if age <= 2:
            price_modifier = 1.2  # زيادة 20% للسيارات الجديدة
        elif age <= 5:
            price_modifier = 1.0  # السعر الأساسي
        elif age <= 10:
            price_modifier = 0.8  # خصم 20%
        else:
            price_modifier = 0.6  # خصم 40% للسيارات القديمة
        
        suggested_daily = int(base_price * price_modifier)
        suggested_monthly = int(suggested_daily * 25)  # خصم 5 أيام
        suggested_yearly = int(suggested_monthly * 11)  # خصم شهر
        
        # أسعار مع سائق (زيادة 80-120%)
        driver_multiplier = 1.9
        suggested_daily_driver = int(suggested_daily * driver_multiplier)
        suggested_monthly_driver = int(suggested_monthly * driver_multiplier)
        
        # اقتراح سياسة الاستخدام
        suggested_km_limit = 200 if car_category == 'Luxury' else 250
        suggested_extra_km_cost = round(suggested_daily / suggested_km_limit * 1.5, 1)
        
        return Response({
            'car_info': {
                'type': car_type,
                'category': car_category,
                'year': year,
                'age': age
            },
            'suggested_pricing': {
                'without_driver': {
                    'daily': suggested_daily,
                    'monthly': suggested_monthly,
                    'yearly': suggested_yearly
                },
                'with_driver': {
                    'daily': suggested_daily_driver,
                    'monthly': suggested_monthly_driver
                }
            },
            'suggested_policy': {
                'daily_km_limit': suggested_km_limit,
                'extra_km_cost': suggested_extra_km_cost,
                'daily_hour_limit': 12,
                'extra_hour_cost': round(suggested_daily / 12, 1)
            },
            'market_analysis': {
                'price_range': {
                    'min': int(suggested_daily * 0.8),
                    'max': int(suggested_daily * 1.2)
                },
                'competitiveness': 'Average' if 200 <= suggested_daily <= 500 else 
                                 'Budget' if suggested_daily < 200 else 'Premium'
            },
            'recommendations': [
                f'Consider pricing between {int(suggested_daily * 0.9)} - {int(suggested_daily * 1.1)} EGP/day',
                'Monitor competitor prices in your area',
                'Adjust pricing based on demand and seasonality'
            ]
        })

# ==================== TEST APIs للمراحل المختلفة ====================

class TestCarBasicInfoView(APIView):
    """
    تيست المرحلة الأولى: البيانات الأساسية للعربية
    POST /api/cars/test/basic-info/
    """
    permission_classes = [IsAuthenticated]
    
    def post(self, request):
        data = request.data
        errors = {}
        warnings = []
        
        # التحقق من الحقول المطلوبة
        required_fields = {
            'model': 'موديل العربية مطلوب',
            'brand': 'ماركة العربية مطلوبة', 
            'car_type': 'نوع العربية مطلوب',
            'car_category': 'فئة العربية مطلوبة',
            'plate_number': 'رقم اللوحة مطلوب',
            'year': 'سنة الصنع مطلوبة',
            'color': 'لون العربية مطلوب',
            'seating_capacity': 'عدد المقاعد مطلوب',
            'transmission_type': 'نوع ناقل الحركة مطلوب',
            'fuel_type': 'نوع الوقود مطلوب',
            'current_odometer_reading': 'قراءة العداد الحالية مطلوبة'
        }
        
        for field, message in required_fields.items():
            if not data.get(field):
                errors[field] = message
        
        # التحقق من رقم اللوحة والعربيات المشابهة
        plate_number = data.get('plate_number')
        existing_car_info = None
        similar_cars = []
        
        if plate_number:
            # تحقق من التنسيق
            if not re.match(r'^[أ-ي\s\d]+$', plate_number) and not re.match(r'^[A-Z\s\d]+$', plate_number):
                errors['plate_number'] = 'تنسيق رقم اللوحة غير صحيح'
            
            # تحقق من عدم التكرار
            existing_car = Car.objects.filter(plate_number=plate_number).first()  # type: ignore
            if existing_car:
                existing_car_info = {
                    'id': existing_car.id,
                    'model': existing_car.model,
                    'brand': existing_car.brand,
                    'year': existing_car.year,
                    'owner_is_you': existing_car.owner == request.user,
                    'status': existing_car.current_status
                }
                if existing_car.owner == request.user:
                    errors['plate_number'] = 'لديك عربية بنفس رقم اللوحة بالفعل'
                else:
                    errors['plate_number'] = 'رقم اللوحة مستخدم من مالك آخر'
        
        # البحث عن عربيات مشابهة للمستخدم
        if data.get('model') and data.get('brand'):
            user_similar = Car.objects.filter(  # type: ignore
                owner=request.user,
                model__icontains=data['model'],
                brand__icontains=data['brand']
            )[:5]  # أول 5 عربيات مشابهة
            
            for car in user_similar:
                similar_cars.append({
                    'id': car.id,
                    'model': car.model,
                    'brand': car.brand,
                    'year': car.year,
                    'plate_number': car.plate_number,
                    'status': car.current_status,
                    'match_level': 'دقيق' if car.model.lower() == data['model'].lower() else 'مشابه'
                })
            
            if user_similar.exists():
                warnings.append(f'لديك {user_similar.count()} عربية مشابهة بالفعل')
        
        # التحقق من السنة
        year = data.get('year')
        if year:
            try:
                year = int(year)
                if year < 1990 or year > 2025:
                    errors['year'] = 'السنة يجب أن تكون بين 1990 و 2025'
                elif year < 2010:
                    warnings.append('السيارات الأقدم من 2010 قد تقل عليها الطلبات')
            except (ValueError, TypeError):
                errors['year'] = 'تنسيق السنة غير صحيح'
        
        # التحقق من عدد المقاعد
        seating_capacity = data.get('seating_capacity')
        if seating_capacity:
            try:
                capacity = int(seating_capacity)
                if capacity < 2 or capacity > 15:
                    errors['seating_capacity'] = 'عدد المقاعد يجب أن يكون بين 2 و 15'
            except (ValueError, TypeError):
                errors['seating_capacity'] = 'تنسيق عدد المقاعد غير صحيح'
        
        # التحقق من قراءة العداد
        odometer = data.get('current_odometer_reading')
        if odometer:
            try:
                odometer_val = int(odometer)
                if odometer_val < 0:
                    errors['current_odometer_reading'] = 'قراءة العداد لا يمكن أن تكون سالبة'
                elif odometer_val > 500000:
                    warnings.append('قراءة العداد عالية وقد تؤثر على جاذبية الإيجار')
            except (ValueError, TypeError):
                errors['current_odometer_reading'] = 'تنسيق قراءة العداد غير صحيح'
        
        # التحقق من الخيارات المحددة
        valid_choices = {
            'car_type': [choice[0] for choice in Car.CAR_TYPE_CHOICES],
            'car_category': [choice[0] for choice in Car.CAR_CATEGORY_CHOICES],
            'transmission_type': [choice[0] for choice in Car.TRANSMISSION_CHOICES],
            'fuel_type': [choice[0] for choice in Car.FUEL_CHOICES]
        }
        
        for field, choices in valid_choices.items():
            value = data.get(field)
            if value and value not in choices:
                errors[field] = f'خيار غير صحيح. الخيارات المتاحة: {", ".join(choices)}'
        
        is_valid = len(errors) == 0
        
        # إحصائيات السوق
        market_stats = None
        if data.get('car_type'):
            total_cars = Car.objects.filter(car_type=data['car_type']).count()  # type: ignore
            market_stats = {
                'total_cars_of_type': total_cars,
                'popularity': 'عالي' if total_cars > 50 else 'متوسط' if total_cars > 20 else 'منخفض'
            }
        
        return Response({
            'stage': 'basic_info',
            'valid': is_valid,
            'errors': errors,
            'warnings': warnings,
            'message': 'البيانات الأساسية صحيحة!' if is_valid else 'يرجى تصحيح الأخطاء أعلاه',
            'next_step': 'rental_options' if is_valid else None,
            'existing_car_check': {
                'plate_available': existing_car_info is None,
                'existing_car': existing_car_info,
                'similar_cars': similar_cars,
                'similar_count': len(similar_cars)
            },
            'market_stats': market_stats
        })


class TestCarRentalOptionsView(APIView):
    """
    تيست المرحلة الثانية: خيارات الإيجار والأسعار
    POST /api/cars/test/rental-options/
    """
    permission_classes = [IsAuthenticated]
    
    def post(self, request):
        data = request.data
        errors = {}
        warnings = []
        
        # التحقق من توفر خيار واحد على الأقل
        without_driver = data.get('available_without_driver', False)
        with_driver = data.get('available_with_driver', False)
        
        if not without_driver and not with_driver:
            errors['availability'] = 'يجب تفعيل خيار واحد على الأقل (مع أو بدون سائق)'
        
        # التحقق من الأسعار بدون سائق
        if without_driver:
            daily_price = data.get('daily_rental_price')
            if not daily_price:
                errors['daily_rental_price'] = 'السعر اليومي مطلوب عند التفعيل بدون سائق'
            else:
                try:
                    price = float(daily_price)
                    if price <= 0:
                        errors['daily_rental_price'] = 'السعر يجب أن يكون أكبر من صفر'
                    elif price < 100:
                        warnings.append('السعر اليومي منخفض، فكر في أسعار السوق')
                    elif price > 2000:
                        warnings.append('السعر اليومي مرتفع، قد يقلل من الحجوزات')
                except (ValueError, TypeError):
                    errors['daily_rental_price'] = 'تنسيق السعر غير صحيح'
            
            # التحقق من السعر الشهري (اختياري)
            monthly_price = data.get('monthly_rental_price')
            if monthly_price:
                try:
                    monthly = float(monthly_price)
                    daily = float(daily_price) if daily_price else 0
                    if monthly > 0 and daily > 0:
                        expected_monthly = daily * 25  # خصم 5 أيام للشهر
                        if monthly > expected_monthly:
                            warnings.append(f'السعر الشهري مرتفع مقارنة باليومي. المقترح: {expected_monthly}')
                except (ValueError, TypeError):
                    errors['monthly_rental_price'] = 'تنسيق السعر الشهري غير صحيح'
        
        # التحقق من الأسعار مع سائق
        if with_driver:
            daily_with_driver = data.get('daily_rental_price_with_driver')
            if not daily_with_driver:
                errors['daily_rental_price_with_driver'] = 'السعر اليومي مع سائق مطلوب'
            else:
                try:
                    price_with_driver = float(daily_with_driver)
                    if price_with_driver <= 0:
                        errors['daily_rental_price_with_driver'] = 'السعر يجب أن يكون أكبر من صفر'
                    
                    # مقارنة مع السعر بدون سائق
                    daily_without = data.get('daily_rental_price')
                    if daily_without:
                        try:
                            without_price = float(daily_without)
                            if price_with_driver <= without_price:
                                errors['daily_rental_price_with_driver'] = 'السعر مع سائق يجب أن يكون أعلى من بدون سائق'
                            elif price_with_driver < without_price * 1.5:
                                warnings.append('السعر مع سائق قد يكون منخفض مقارنة ببدون سائق')
                        except (ValueError, TypeError):
                            pass
                except (ValueError, TypeError):
                    errors['daily_rental_price_with_driver'] = 'تنسيق السعر غير صحيح'
        
        # مقارنة الأسعار مع السوق
        market_comparison = None
        if data.get('daily_rental_price'):
            from django.db.models import Avg
            avg_market_price = CarRentalOptions.objects.aggregate(  # type: ignore
                avg=Avg('daily_rental_price')
            )['avg'] or 300
            
            user_price = float(data['daily_rental_price'])
            difference = ((user_price - avg_market_price) / avg_market_price) * 100
            
            market_comparison = {
                'market_average': round(avg_market_price, 2),
                'your_price': user_price,
                'difference_percent': round(difference, 1),
                'status': 'أعلى من السوق' if difference > 10 else 'أقل من السوق' if difference < -10 else 'مطابق للسوق'
            }
        
        # تحقق من أسعار المستخدم السابقة
        user_history = []
        user_cars = Car.objects.filter(owner=request.user).select_related('rental_options')  # type: ignore
        for car in user_cars[:3]:  # آخر 3 عربيات
            if hasattr(car, 'rental_options') and car.rental_options.daily_rental_price:
                user_history.append({
                    'car': f'{car.brand} {car.model}',
                    'price': float(car.rental_options.daily_rental_price),
                    'year': car.year
                })
        
        is_valid = len(errors) == 0
        
        return Response({
            'stage': 'rental_options',
            'valid': is_valid,
            'errors': errors,
            'warnings': warnings,
            'message': 'خيارات الإيجار صحيحة!' if is_valid else 'يرجى تصحيح الأخطاء أعلاه',
            'next_step': 'usage_policy' if is_valid else None,
            'market_comparison': market_comparison,
            'user_price_history': user_history,
            'pricing_tips': [
                'السعر المعقول يجذب المزيد من العملاء',
                'راقب أسعار المنافسين في منطقتك',
                'يمكنك تعديل الأسعار لاحقاً حسب الطلب'
            ]
        })


class TestCarUsagePolicyView(APIView):
    """
    تيست المرحلة الثالثة: سياسة الاستخدام
    POST /api/cars/test/usage-policy/
    """
    permission_classes = [IsAuthenticated]
    
    def post(self, request):
        data = request.data
        errors = {}
        warnings = []
        
        # التحقق من حد الكيلومترات اليومي
        daily_km_limit = data.get('daily_km_limit')
        if not daily_km_limit:
            errors['daily_km_limit'] = 'حد الكيلومترات اليومي مطلوب'
        else:
            try:
                km_limit = float(daily_km_limit)
                if km_limit <= 0:
                    errors['daily_km_limit'] = 'حد الكيلومترات يجب أن يكون أكبر من صفر'
                elif km_limit < 100:
                    warnings.append('حد الكيلومترات منخفض وقد يثني المستأجرين')
                elif km_limit > 500:
                    warnings.append('حد الكيلومترات مرتفع وقد يزيد التكاليف')
            except (ValueError, TypeError):
                errors['daily_km_limit'] = 'تنسيق حد الكيلومترات غير صحيح'
        
        # التحقق من تكلفة الكيلو الإضافي
        extra_km_cost = data.get('extra_km_cost')
        if not extra_km_cost:
            errors['extra_km_cost'] = 'تكلفة الكيلو الإضافي مطلوبة'
        else:
            try:
                km_cost = float(extra_km_cost)
                if km_cost <= 0:
                    errors['extra_km_cost'] = 'تكلفة الكيلو الإضافي يجب أن تكون أكبر من صفر'
                elif km_cost < 0.5:
                    warnings.append('تكلفة الكيلو الإضافي منخفضة وقد تشجع على الإفراط')
                elif km_cost > 5:
                    warnings.append('تكلفة الكيلو الإضافي مرتفعة وقد تثني عن الإيجار')
            except (ValueError, TypeError):
                errors['extra_km_cost'] = 'تنسيق تكلفة الكيلو الإضافي غير صحيح'
        
        # التحقق من حد الساعات اليومي (اختياري)
        daily_hour_limit = data.get('daily_hour_limit')
        if daily_hour_limit:
            try:
                hour_limit = int(daily_hour_limit)
                if hour_limit <= 0:
                    errors['daily_hour_limit'] = 'حد الساعات يجب أن يكون أكبر من صفر'
                elif hour_limit > 24:
                    errors['daily_hour_limit'] = 'حد الساعات لا يمكن أن يتجاوز 24 ساعة'
                elif hour_limit < 8:
                    warnings.append('حد الساعات منخفض وقد يكون مقيد')
                
                # التحقق من تكلفة الساعة الإضافية
                extra_hour_cost = data.get('extra_hour_cost')
                if not extra_hour_cost:
                    errors['extra_hour_cost'] = 'تكلفة الساعة الإضافية مطلوبة عند تحديد حد الساعات'
                else:
                    try:
                        hour_cost = float(extra_hour_cost)
                        if hour_cost <= 0:
                            errors['extra_hour_cost'] = 'تكلفة الساعة الإضافية يجب أن تكون أكبر من صفر'
                    except (ValueError, TypeError):
                        errors['extra_hour_cost'] = 'تنسيق تكلفة الساعة الإضافية غير صحيح'
            except (ValueError, TypeError):
                errors['daily_hour_limit'] = 'تنسيق حد الساعات غير صحيح'
        
        # تحقق من التوازن بين السعر وحد الكيلومترات
        daily_price = data.get('daily_rental_price')  # من المرحلة السابقة
        if daily_price and daily_km_limit and extra_km_cost:
            try:
                price = float(daily_price)
                limit = float(daily_km_limit)
                cost = float(extra_km_cost)
                
                cost_per_km = price / limit
                if cost < cost_per_km * 0.5:
                    warnings.append('تكلفة الكيلو الإضافي أقل بكثير من التكلفة الأساسية للكيلو')
                elif cost > cost_per_km * 3:
                    warnings.append('تكلفة الكيلو الإضافي أعلى بكثير من التكلفة الأساسية للكيلو')
            except (ValueError, TypeError):
                pass
        
        # مقارنة مع سياسات المستخدم السابقة
        user_policies = []
        user_cars = Car.objects.filter(owner=request.user).select_related('usage_policy')  # type: ignore
        for car in user_cars[:3]:
            if hasattr(car, 'usage_policy'):
                policy = car.usage_policy
                user_policies.append({
                    'car': f'{car.brand} {car.model}',
                    'daily_km_limit': float(policy.daily_km_limit),
                    'extra_km_cost': float(policy.extra_km_cost),
                    'year': car.year
                })
        
        # إحصائيات السوق
        market_stats = None
        if data.get('daily_km_limit') and data.get('extra_km_cost'):
            from django.db.models import Avg
            avg_km_limit = CarUsagePolicy.objects.aggregate(  # type: ignore
                avg=Avg('daily_km_limit')
            )['avg'] or 200
            avg_km_cost = CarUsagePolicy.objects.aggregate(  # type: ignore
                avg=Avg('extra_km_cost')
            )['avg'] or 2.0
            
            market_stats = {
                'market_avg_km_limit': round(avg_km_limit, 2),
                'market_avg_km_cost': round(avg_km_cost, 2),
                'your_km_limit': float(data['daily_km_limit']),
                'your_km_cost': float(data['extra_km_cost']),
                'limit_comparison': 'أعلى من السوق' if float(data['daily_km_limit']) > avg_km_limit else 'أقل من السوق',
                'cost_comparison': 'أعلى من السوق' if float(data['extra_km_cost']) > avg_km_cost else 'أقل من السوق'
            }
        
        is_valid = len(errors) == 0
        
        return Response({
            'stage': 'usage_policy',
            'valid': is_valid,
            'errors': errors,
            'warnings': warnings,
            'message': 'سياسة الاستخدام صحيحة!' if is_valid else 'يرجى تصحيح الأخطاء أعلاه',
            'next_step': 'complete' if is_valid else None,
            'market_comparison': market_stats,
            'user_policy_history': user_policies,
            'policy_tips': [
                'حد الكيلومترات المعقول يجذب المستأجرين',
                'تكلفة إضافية معقولة تحمي سيارتك',
                'راقب كيف يستخدم المستأجرون سياساتك'
            ]
        })


class TestCompleteCarView(APIView):
    """
    تيست نهائي شامل لجميع بيانات العربية
    POST /api/cars/test/complete/
    """
    permission_classes = [IsAuthenticated]
    
    def post(self, request):
        data = request.data
        
        # تشغيل جميع التحققات
        basic_test = TestCarBasicInfoView().post(request)
        rental_test = TestCarRentalOptionsView().post(request)
        policy_test = TestCarUsagePolicyView().post(request)
        
        # جمع النتائج
        all_errors = {}
        all_warnings = []
        
        if basic_test.data['errors']:
            all_errors.update({f"basic_{k}": v for k, v in basic_test.data['errors'].items()})
        if rental_test.data['errors']:
            all_errors.update({f"rental_{k}": v for k, v in rental_test.data['errors'].items()})
        if policy_test.data['errors']:
            all_errors.update({f"policy_{k}": v for k, v in policy_test.data['errors'].items()})
        
        all_warnings.extend([f"البيانات الأساسية: {w}" for w in basic_test.data['warnings']])
        all_warnings.extend([f"خيارات الإيجار: {w}" for w in rental_test.data['warnings']])
        all_warnings.extend([f"سياسة الاستخدام: {w}" for w in policy_test.data['warnings']])
        
        is_valid = len(all_errors) == 0
        
        # حساب معاينة التكاليف
        cost_preview = None
        if is_valid:
            daily_price = data.get('daily_rental_price')
            km_limit = data.get('daily_km_limit')
            if daily_price and km_limit:
                try:
                    price = float(daily_price)
                    limit = float(km_limit)
                    cost_preview = {
                        'daily_cost_per_km': round(price / limit, 2),
                        'weekly_cost': price * 7,
                        'monthly_cost': price * 30,
                        'estimated_monthly_km': limit * 30
                    }
                except (ValueError, TypeError):
                    pass
        
        return Response({
            'stage': 'complete',
            'valid': is_valid,
            'errors': all_errors,
            'warnings': all_warnings,
            'summary': {
                'basic_info_valid': basic_test.data['valid'],
                'rental_options_valid': rental_test.data['valid'],
                'usage_policy_valid': policy_test.data['valid'],
                'ready_to_submit': is_valid
            },
            'cost_preview': cost_preview,
            'message': 'جميع بيانات العربية صحيحة وجاهزة للإرسال!' if is_valid else 'يرجى تصحيح جميع الأخطاء قبل الإرسال',
            'next_action': 'submit_car' if is_valid else 'fix_errors'
        })


# ==================== APIs مساعدة ====================

class QuickPlateCheckView(APIView):
    """
    تحقق سريع من رقم اللوحة
    POST /api/cars/test/plate-check/
    """
    permission_classes = [IsAuthenticated]
    
    def post(self, request):
        plate_number = request.data.get('plate_number')
        
        if not plate_number:
            return Response({'error': 'رقم اللوحة مطلوب'}, status=400)
        
        # تحقق من التنسيق
        is_valid_format = bool(
            re.match(r'^[أ-ي\s\d]+$', plate_number) or 
            re.match(r'^[A-Z\s\d]+$', plate_number)
        )
        
        # تحقق من التوفر والحصول على تفاصيل إن وجدت
        existing_car = Car.objects.filter(plate_number=plate_number).first()  # type: ignore
        is_available = existing_car is None
        
        response_data = {
            'plate_number': plate_number,
            'valid_format': is_valid_format,
            'available': is_available,
            'status': 'متاح' if (is_valid_format and is_available) else 
                     'تنسيق خاطئ' if not is_valid_format else 'موجود بالفعل'
        }
        
        # إذا كانت العربية موجودة، أضف تفاصيلها
        if existing_car:
            response_data['existing_car'] = {
                'id': existing_car.id,
                'model': existing_car.model,
                'brand': existing_car.brand,
                'year': existing_car.year,
                'owner_is_you': existing_car.owner == request.user,
                'status': existing_car.current_status
            }
            
            if existing_car.owner == request.user:
                response_data['message'] = 'هذه عربيتك بالفعل!'
            else:
                response_data['message'] = 'رقم اللوحة مستخدم من مالك آخر'
                
                # اقتراحات أرقام مشابهة
                suggestions = []
                numbers_in_plate = ''.join(filter(str.isdigit, plate_number))
                if numbers_in_plate:
                    try:
                        base_num = int(numbers_in_plate)
                        for i in range(1, 6):
                            new_num = str(base_num + i).zfill(len(numbers_in_plate))
                            suggested = plate_number.replace(numbers_in_plate, new_num)
                            if not Car.objects.filter(plate_number=suggested).exists():  # type: ignore
                                suggestions.append(suggested)
                                if len(suggestions) >= 3:
                                    break
                    except ValueError:
                        pass
                
                if suggestions:
                    response_data['suggestions'] = suggestions
                    response_data['suggestion_message'] = 'اقتراحات متاحة'
        
        return Response(response_data)


class PricingSuggestionsView(APIView):
    """
    اقتراحات أسعار ذكية
    POST /api/cars/test/pricing-suggestions/
    """
    permission_classes = [IsAuthenticated]
    
    def post(self, request):
        car_type = request.data.get('car_type')
        car_category = request.data.get('car_category')
        year = request.data.get('year')
        
        if not all([car_type, car_category, year]):
            return Response({'error': 'نوع العربية وفئتها وسنة الصنع مطلوبة'}, status=400)
        
        try:
            year = int(year)
        except (ValueError, TypeError):
            return Response({'error': 'تنسيق السنة غير صحيح'}, status=400)
        
        # جدول أسعار أساسي
        base_prices = {
            'Economy': {'SUV': 300, 'Sedan': 250, 'Hatchback': 200, 'Other': 220},
            'Luxury': {'SUV': 600, 'Sedan': 500, 'Hatchback': 400, 'Other': 450},
            'Sports': {'SUV': 800, 'Sedan': 700, 'Hatchback': 600, 'Other': 650},
            'Electric': {'SUV': 400, 'Sedan': 350, 'Hatchback': 300, 'Other': 320}
        }
        
        base_price = base_prices.get(car_category, {}).get(car_type, 300)
        
        # تعديل حسب العمر
        current_year = 2024
        age = current_year - year
        if age <= 2:
            modifier = 1.2
        elif age <= 5:
            modifier = 1.0
        elif age <= 10:
            modifier = 0.8
        else:
            modifier = 0.6
        
        suggested_daily = int(base_price * modifier)
        suggested_monthly = int(suggested_daily * 25)
        
        # أسعار مع سائق
        driver_daily = int(suggested_daily * 1.9)
        driver_monthly = int(suggested_monthly * 1.9)
        
        # سياسة استخدام مقترحة
        suggested_km = 200 if car_category == 'Luxury' else 250
        suggested_km_cost = round(suggested_daily / suggested_km * 1.5, 1)
        
        return Response({
            'car_info': {
                'type': car_type,
                'category': car_category,
                'year': year,
                'age': age
            },
            'suggested_prices': {
                'without_driver': {
                    'daily': suggested_daily,
                    'monthly': suggested_monthly
                },
                'with_driver': {
                    'daily': driver_daily,
                    'monthly': driver_monthly
                }
            },
            'suggested_policy': {
                'daily_km_limit': suggested_km,
                'extra_km_cost': suggested_km_cost,
                'daily_hour_limit': 12,
                'extra_hour_cost': round(suggested_daily / 12, 1)
            },
            'price_range': {
                'min': int(suggested_daily * 0.8),
                'max': int(suggested_daily * 1.2)
            },
            'tips': [
                f'اقترح سعر بين {int(suggested_daily * 0.9)} - {int(suggested_daily * 1.1)} جنيه/يوم',
                'راقب أسعار المنافسين في منطقتك',
                'اضبط الأسعار حسب الطلب والموسم'
            ]
        })
