from django.shortcuts import render
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from .models import User, Role, UserRole
from rest_framework import viewsets , generics, permissions
from .models import User, Role, UserRole
from .serializers import RegisterSerializer, RoleSerializer, UserRoleSerializer
from django.contrib.auth import get_user_model
from rest_framework.permissions import IsAuthenticated

User = get_user_model()

class RegisterView(generics.CreateAPIView):
    queryset = User.objects.all()
    permission_classes = (permissions.AllowAny,)
    serializer_class = RegisterSerializer

class RoleViewSet(viewsets.ModelViewSet):
    queryset = Role.objects.all()
    serializer_class = RoleSerializer

class UserRoleViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated]
    queryset = UserRole.objects.all()
    serializer_class = UserRoleSerializer


class AssignRolesAPIView(APIView):
    def post(self, request):
        user_id = request.data.get('user_id')
        role_ids = request.data.get('role_ids', [])

        # إزالة التكرار من الأدوار المرسلة
        role_ids = list(set(role_ids))

        # تحقق من أن اليوزر موجود
        try:
            user = User.objects.get(id=user_id)
        except User.DoesNotExist:
            return Response({"error": "User not found."}, status=status.HTTP_404_NOT_FOUND)

        # تحقق أن كل الرولز المطلوبة موجودة
        roles = Role.objects.filter(id__in=role_ids)
        if roles.count() != len(role_ids):
            return Response({
                "error": "One or more role IDs are invalid.",
                "provided_role_ids": role_ids,
                "valid_role_ids": list(roles.values_list('id', flat=True))
            }, status=status.HTTP_400_BAD_REQUEST)

        # احذف كل الرولز القديمة لهذا اليوزر
        UserRole.objects.filter(user=user).delete()

        # أضف الرولز الجديدة
        added_roles = []
        for role in roles:
            UserRole.objects.create(user=user, role=role)
            added_roles.append(role.role_name)

        return Response({
            "message": "Roles reassigned successfully.",
            "user_id": user.id,
            "assigned_roles": added_roles
        }, status=status.HTTP_200_OK)

class UserRolesAPIView(APIView):
    def get(self, request, user_id):
        try:
            user = User.objects.get(id=user_id)
        except User.DoesNotExist:
            return Response({"error": "User not found."}, status=status.HTTP_404_NOT_FOUND)

        user_roles = UserRole.objects.filter(user=user).select_related('role')
        roles = [{"id": ur.role.id, "name": ur.role.role_name} for ur in user_roles]

        return Response({
            "user_id": user.id,
            "email": user.email,
            "roles": roles
        }, status=status.HTTP_200_OK)