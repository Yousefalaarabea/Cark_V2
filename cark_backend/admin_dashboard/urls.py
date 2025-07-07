from django.urls import path, include
from django.contrib import admin
from rest_framework.routers import DefaultRouter
from .views import (
    AdminDashboardView, AdminCarViewSet, AdminDocumentViewSet, 
    AdminUserViewSet, AdminRentalViewSet, AdminRatingViewSet,
    AdminActionViewSet, SystemAlertViewSet
)

router = DefaultRouter()
router.register(r'cars', AdminCarViewSet, basename='admin-car')
router.register(r'documents', AdminDocumentViewSet, basename='admin-document')
router.register(r'users', AdminUserViewSet, basename='admin-user')
router.register(r'rentals', AdminRentalViewSet, basename='admin-rental')
router.register(r'ratings', AdminRatingViewSet, basename='admin-rating')
router.register(r'actions', AdminActionViewSet, basename='admin-action')
router.register(r'alerts', SystemAlertViewSet, basename='admin-alert')

urlpatterns = [
    path('dashboard/', AdminDashboardView.as_view(), name='admin-dashboard'),
    path('', include(router.urls)),
    

] 