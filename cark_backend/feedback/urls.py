from django.urls import path
from .views import RateOwnerView, RateRenterView, RateCarView, CreateReportView, AdminNegativeRatingsView, AdminNewReportsView

urlpatterns = [
    # New specific rating endpoints
    path('rate/owner/', RateOwnerView.as_view(), name='rate-owner'),
    path('rate/renter/', RateRenterView.as_view(), name='rate-renter'), 
    path('rate/car/', RateCarView.as_view(), name='rate-car'),
    
    # Other endpoints
    path('report/', CreateReportView.as_view(), name='report'),
    path('admin/ratings/', AdminNegativeRatingsView.as_view(), name='admin-negative-ratings'),
    path('admin/reports/', AdminNewReportsView.as_view(), name='admin-new-reports'),
] 