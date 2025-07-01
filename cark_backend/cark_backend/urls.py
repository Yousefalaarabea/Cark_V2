from django.contrib import admin
from django.urls import path, include
from django.conf.urls.static import static
from django.conf import settings


urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/', include('users.urls')),  # إضافة رابط الـ API
    path('api/', include('cars.urls')),  # إضافة رابط الـ API للسيارات
    path('api/', include('documents.urls')),  # إضافة رابط الـ API للمستندات
    path('api/', include('rentals.urls')),  # إضافة رابط الـ API للايجارات
    path('api/', include('selfdrive_rentals.urls')),  # إضافة رابط الـ API للايجار بدون سائق
    path('api/payments/', include('payments.urls')),  # إضافة رابط الـ API للمدفوعات
    path('api/wallets/', include('wallets.urls')),  # إضافة رابط الـ API للمحفظة
    path('api/feedback/', include('feedback.urls')),  # إضافة رابط الـ API للتقييمات والتقارير
]

 #أثناء التطوير فقط: السماح لخادم Django أن يخدم ملفات الميديا
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

