from rest_framework.routers import DefaultRouter
from .views import (
    SelfDriveRentalViewSet, NewCardDepositPaymentView, PriceCalculatorView,
    OwnerPendingPaymentsView, RentalStatusTimelineView, RentalDashboardView,
    CalculateExcessView, RenterDropoffPreviewView, OwnerDropoffPreviewView,
    RentalSummaryView
)

router = DefaultRouter()
router.register(r'selfdrive-rentals', SelfDriveRentalViewSet, basename='selfdrive-rental')

urlpatterns = router.urls

# Additional endpoints
from django.urls import path
urlpatterns += [
    # Payment endpoints
    path('selfdrive-rentals/<int:rental_id>/new_card_deposit_payment/', NewCardDepositPaymentView.as_view()),
    
    # New utility endpoints
    path('selfdrive-rentals/calculate-price/', PriceCalculatorView.as_view(), name='calculate-price'),
    path('selfdrive-rentals/owner/pending-payments/', OwnerPendingPaymentsView.as_view(), name='owner-pending-payments'),
    path('selfdrive-rentals/<int:rental_id>/timeline/', RentalStatusTimelineView.as_view(), name='rental-timeline'),
    path('selfdrive-rentals/dashboard/', RentalDashboardView.as_view(), name='rental-dashboard'),
    
    # Drop-off handover endpoints
    path('selfdrive-rentals/<int:rental_id>/calculate-excess/', CalculateExcessView.as_view(), name='calculate-excess'),
    path('selfdrive-rentals/<int:rental_id>/renter-dropoff-preview/', RenterDropoffPreviewView.as_view(), name='renter-dropoff-preview'),
    path('selfdrive-rentals/<int:rental_id>/owner-dropoff-preview/', OwnerDropoffPreviewView.as_view(), name='owner-dropoff-preview'),
    path('selfdrive-rentals/<int:rental_id>/summary/', RentalSummaryView.as_view(), name='rental-summary'),
]
