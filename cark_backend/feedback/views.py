from django.shortcuts import render
from rest_framework import generics, permissions, status
from rest_framework.response import Response
from .models import Rating, Report
from .serializers import (
    RatingSerializer, 
    ReportSerializer,
    RateOwnerSerializer,
    RateRenterSerializer,
    RateCarSerializer
)
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
from rest_framework.exceptions import ValidationError


# Create your views here.

class RateOwnerView(generics.CreateAPIView):
    """
    Rate the car owner (for renters)
    Body: {
        "rental_type": "rental" or "selfdriverental",
        "rental_id": 1,
        "rating": 5,
        "notes": "Great owner!"
    }
    """
    serializer_class = RateOwnerSerializer
    permission_classes = [permissions.IsAuthenticated]


class RateRenterView(generics.CreateAPIView):
    """
    Rate the renter (for owners)
    Body: {
        "rental_type": "rental" or "selfdriverental", 
        "rental_id": 1,
        "rating": 5,
        "notes": "Great renter!"
    }
    """
    serializer_class = RateRenterSerializer
    permission_classes = [permissions.IsAuthenticated]


class RateCarView(generics.CreateAPIView):
    """
    Rate the car (for renters only)
    Body: {
        "rental_type": "rental" or "selfdriverental",
        "rental_id": 1, 
        "rating": 5,
        "notes": "Great car!"
    }
    """
    serializer_class = RateCarSerializer
    permission_classes = [permissions.IsAuthenticated]

class CreateReportView(generics.CreateAPIView):
    serializer_class = ReportSerializer
    permission_classes = [permissions.IsAuthenticated]

    def perform_create(self, serializer):
        target_type = self.request.data.get('target_type')  # type: ignore
        target_id = self.request.data.get('target_id')  # type: ignore
        user = self.request.user
        from users.models import UserRole
        from cars.models import Car
        from rentals.models import Rental
        from selfdrive_rentals.models import SelfDriveRental
        if target_type == 'user':
            try:
                userrole = UserRole.objects.get(id=target_id)  # type: ignore
            except UserRole.DoesNotExist:  # type: ignore
                raise serializers.ValidationError('UserRole does not exist.')
            rental_exists = Rental.objects.filter(Q(owner=user, renter=userrole.user) | Q(owner=userrole.user, renter=user)).exists()  # type: ignore
            selfdrive_exists = SelfDriveRental.objects.filter(Q(owner=user, renter=userrole.user) | Q(owner=userrole.user, renter=user)).exists()  # type: ignore
            if not (rental_exists or selfdrive_exists):
                raise serializers.ValidationError('You can only report users you have shared a rental with.')
        elif target_type == 'car':
            try:
                car = Car.objects.get(id=target_id)  # type: ignore
            except Car.DoesNotExist:  # type: ignore
                raise serializers.ValidationError('Car does not exist.')
            rental_exists = Rental.objects.filter(Q(car=car) & (Q(owner=user) | Q(renter=user))).exists()  # type: ignore
            selfdrive_exists = SelfDriveRental.objects.filter(Q(car=car) & (Q(owner=user) | Q(renter=user))).exists()  # type: ignore
            if not (rental_exists or selfdrive_exists):
                raise serializers.ValidationError('You can only report cars you have used in a rental.')
        serializer.save()

class AdminNegativeRatingsView(generics.ListAPIView):
    serializer_class = RatingSerializer
    permission_classes = [permissions.IsAdminUser]

    def get_queryset(self):
        return Rating.objects.filter(rating__lt=3).order_by('-created_at')  # type: ignore

class AdminNewReportsView(generics.ListAPIView):
    serializer_class = ReportSerializer
    permission_classes = [permissions.IsAdminUser]

    def get_queryset(self):
        return Report.objects.filter(status='pending').order_by('-created_at')  # type: ignore
