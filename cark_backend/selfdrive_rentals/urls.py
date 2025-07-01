from rest_framework.routers import DefaultRouter
from .views import SelfDriveRentalViewSet, NewCardDepositPaymentView

router = DefaultRouter()
router.register(r'selfdrive-rentals', SelfDriveRentalViewSet, basename='selfdrive-rental')

urlpatterns = router.urls

# إضافة endpoint جديد للدفع بكارت جديد
from django.urls import path
urlpatterns += [
    path('selfdrive-rentals/<int:rental_id>/new_card_deposit_payment/', NewCardDepositPaymentView.as_view()),
]
