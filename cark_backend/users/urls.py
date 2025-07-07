from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import RoleViewSet, UserRoleViewSet , RegisterView   , AssignRolesAPIView , UserRolesAPIView, UserViewSet, UpdateUserPermissionsAPIView, CustomTokenObtainPairView
from rest_framework_simplejwt.views import TokenRefreshView

router = DefaultRouter()
router.register(r'roles', RoleViewSet)
router.register(r'user-roles', UserRoleViewSet)
router.register(r'users', UserViewSet)




urlpatterns = [
    path('register/', RegisterView.as_view(), name='register'),
    path('login/', CustomTokenObtainPairView.as_view(), name='token_obtain_pair'),
    path('token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),
    path('assign-roles/', AssignRolesAPIView.as_view(), name='assign-roles'),
    path('user-roles/<int:user_id>/', UserRolesAPIView.as_view(), name='user-roles'),
    path('update-permissions/<int:user_id>/', UpdateUserPermissionsAPIView.as_view(), name='update-user-permissions'),
    path('', include(router.urls))
]

