from django.urls import path, include
from rest_framework.routers import DefaultRouter
from . import views

router = DefaultRouter()
router.register(r'rentals', views.RentalViewSet, basename='rental')

urlpatterns = [
    path('', views.home, name='home'),  # مثال على رابط
    path('', include(router.urls)),
    # أضف روابط أخرى هنا حسب الحاجة
]
