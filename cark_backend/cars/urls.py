from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import CarViewSet, CarRentalOptionsViewSet, CarUsagePolicyViewSet, CarStatsViewSet, MyCarsView

router = DefaultRouter()
router.register(r'cars', CarViewSet)
router.register(r'rental-options', CarRentalOptionsViewSet)
router.register(r'usage-policies', CarUsagePolicyViewSet)
router.register(r'stats', CarStatsViewSet)

urlpatterns = [
    path('', include(router.urls)),
    path('my-cars/', MyCarsView.as_view(), name='my-cars'), 
]
