from django.urls import path
from .views import CreateRatingView, CreateReportView, AdminNegativeRatingsView, AdminNewReportsView

urlpatterns = [
    path('rate/', CreateRatingView.as_view(), name='rate'),
    path('report/', CreateReportView.as_view(), name='report'),
    path('admin/ratings/', AdminNegativeRatingsView.as_view(), name='admin-negative-ratings'),
    path('admin/reports/', AdminNewReportsView.as_view(), name='admin-new-reports'),
] 