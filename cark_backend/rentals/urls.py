from django.urls import path, include
from rest_framework.routers import DefaultRouter
from . import views

router = DefaultRouter()
router.register(r'rentals', views.RentalViewSet, basename='rental')

urlpatterns = [
    path('', views.home, name='home'),  # مثال على رابط
    path('', include(router.urls)),
    # New card deposit payment API (same as self-drive)
    path('rentals/<int:rental_id>/new_card_deposit_payment/', views.NewCardDepositPaymentView.as_view(), name='new_card_deposit_payment'),
]
