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