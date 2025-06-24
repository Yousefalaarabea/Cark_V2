from django.contrib import admin
from django.urls import path, include
from django.conf.urls.static import static
from django.conf import settings


urlpatterns = [
    path('', lambda request: JsonResponse({"message": "Welcome to Carك API"})),  # الصفحة الرئيسية
    path('admin/', admin.site.urls),
    path('api/', include('users.urls')),  # إضافة رابط الـ API
    path('api/', include('cars.urls')),  # إضافة رابط الـ API للسيارات
    path('api/', include('documents.urls')),  # إضافة رابط الـ API للمستندات
    path('api/', include('rentals.urls')),  # إضافة رابط الـ API للايجارات
    
]

 #أثناء التطوير فقط: السماح لخادم Django أن يخدم ملفات الميديا
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

