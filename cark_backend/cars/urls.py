from .views import (
    CarViewSet, CarRentalOptionsViewSet, CarUsagePolicyViewSet, CarStatsViewSet, MyCarsView,
    TestCarBasicInfoView, TestCarRentalOptionsView, TestCarUsagePolicyView, 
    TestCompleteCarView, QuickPlateCheckView, PricingSuggestionsView
)

router = DefaultRouter()
router.register(r'cars', CarViewSet)
router.register(r'car-rental-options', CarRentalOptionsViewSet)
router.register(r'car-usage-policy', CarUsagePolicyViewSet)
router.register(r'car-stats', CarStatsViewSet)

urlpatterns = [
    path('', include(router.urls)),
    path('my-cars/', MyCarsView.as_view(), name='my-cars'),
    
    # Test APIs للمراحل المختلفة
    path('cars/test/basic-info/', TestCarBasicInfoView.as_view(), name='test-car-basic-info'),
    path('cars/test/rental-options/', TestCarRentalOptionsView.as_view(), name='test-car-rental-options'),
    path('cars/test/usage-policy/', TestCarUsagePolicyView.as_view(), name='test-car-usage-policy'),
    path('cars/test/complete/', TestCompleteCarView.as_view(), name='test-car-complete'),
    
    # APIs مساعدة
    path('cars/test/plate-check/', QuickPlateCheckView.as_view(), name='quick-plate-check'),
    path('cars/test/pricing-suggestions/', PricingSuggestionsView.as_view(), name='pricing-suggestions'),
]
