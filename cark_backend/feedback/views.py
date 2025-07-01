from django.shortcuts import render
from rest_framework import generics, permissions, status
from rest_framework.response import Response
from .models import Rating, Report
from .serializers import RatingSerializer, ReportSerializer
from django.utils import timezone
from rentals.models import Rental
from selfdrive_rentals.models import SelfDriveRental
from django.contrib.contenttypes.models import ContentType
from datetime import timedelta
from users.models import UserRole
from django.db import models
from cars.models import Car
from django.db.models import Q
from rest_framework import serializers


# Create your views here.

class CreateRatingView(generics.CreateAPIView):
    serializer_class = RatingSerializer
    permission_classes = [permissions.IsAuthenticated]

    def perform_create(self, serializer):
        rental_type = self.request.data.get('rental_type')
        rental_id = self.request.data.get('rental_id')
        user = self.request.user
        # تحقق من أن المستخدم مشارك في الرحلة
        if rental_type == 'rental':
            rental = Rental.objects.get(id=rental_id)

            if not (user == rental.owner or user == rental.renter):
                raise PermissionError('You are not a participant in this rental.')
        elif rental_type == 'selfdriverental':
            rental = SelfDriveRental.objects.get(id=rental_id)
            if not (user == rental.owner or user == rental.renter):
                raise PermissionError('You are not a participant in this selfdrive rental.')
        else:
            raise Exception('Invalid rental type')
        # enforce rental finished and 3-day window
        if rental.status != 'finished':
            raise Exception('Cannot rate before rental is finished.')
        if timezone.now() > rental.end_time + timedelta(days=3):
            raise Exception('Rating period expired.')
        # prevent duplicate rating
        content_type = ContentType.objects.get(model=rental_type)
        if Rating.objects.filter(reviewer=user, rental_content_type=content_type, rental_object_id=rental_id).exists():
            raise Exception('You have already rated this rental.')
        serializer.save()

class CreateReportView(generics.CreateAPIView):
    serializer_class = ReportSerializer
    permission_classes = [permissions.IsAuthenticated]

    def perform_create(self, serializer):
        target_type = self.request.data.get('target_type')
        target_id = self.request.data.get('target_id')
        user = self.request.user
        from users.models import UserRole
        from cars.models import Car
        from rentals.models import Rental
        from selfdrive_rentals.models import SelfDriveRental
        if target_type == 'user':
            try:
                userrole = UserRole.objects.get(id=target_id)
            except UserRole.DoesNotExist:
                raise serializers.ValidationError('UserRole does not exist.')
            rental_exists = Rental.objects.filter(Q(owner=user, renter=userrole.user) | Q(owner=userrole.user, renter=user)).exists()
            selfdrive_exists = SelfDriveRental.objects.filter(Q(owner=user, renter=userrole.user) | Q(owner=userrole.user, renter=user)).exists()
            if not (rental_exists or selfdrive_exists):
                raise serializers.ValidationError('You can only report users you have shared a rental with.')
        elif target_type == 'car':
            try:
                car = Car.objects.get(id=target_id)
            except Car.DoesNotExist:
                raise serializers.ValidationError('Car does not exist.')
            rental_exists = Rental.objects.filter(Q(car=car) & (Q(owner=user) | Q(renter=user))).exists()
            selfdrive_exists = SelfDriveRental.objects.filter(Q(car=car) & (Q(owner=user) | Q(renter=user))).exists()
            if not (rental_exists or selfdrive_exists):
                raise serializers.ValidationError('You can only report cars you have used in a rental.')
        serializer.save()

class AdminNegativeRatingsView(generics.ListAPIView):
    serializer_class = RatingSerializer
    permission_classes = [permissions.IsAdminUser]

    def get_queryset(self):
        return Rating.objects.filter(rating__lt=3).order_by('-created_at')

class AdminNewReportsView(generics.ListAPIView):
    serializer_class = ReportSerializer
    permission_classes = [permissions.IsAdminUser]

    def get_queryset(self):
        return Report.objects.filter(status='pending').order_by('-created_at')
