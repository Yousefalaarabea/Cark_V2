from rest_framework.routers import DefaultRouter
from .views import SelfDriveRentalViewSet

router = DefaultRouter()
router.register(r'selfdrive-rentals', SelfDriveRentalViewSet, basename='selfdrive-rental')

urlpatterns = router.urls
