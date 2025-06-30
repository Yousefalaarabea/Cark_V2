from rest_framework import serializers
from .models import User, Role, UserRole
from django.contrib.auth import get_user_model
import re


User = get_user_model()


class RegisterSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ['id', 'email', 'phone_number', 'first_name', 'last_name', 'national_id', 'date_joined', 'updated_at', 'last_login', 'is_active', 'is_staff', 'is_superuser', 'email_verified', 'password']
        extra_kwargs = {'password': {'write_only': True}}

    def validate_email(self, value):
        if User.objects.filter(email=value).exists():
            raise serializers.ValidationError("Email is already registered.")
        if not re.match(r"[^@]+@[^@]+\.[^@]+", value):
            raise serializers.ValidationError("Enter a valid email address.")
        return value

    def validate_national_id(self, value):
        if not value.isdigit():
            raise serializers.ValidationError("National ID must contain only digits.")
        if len(value) != 14:
            raise serializers.ValidationError("National ID must be exactly 14 digits.")
        if User.objects.filter(national_id=value).exists():
            raise serializers.ValidationError("This National ID is already registered.")
        return value

    def validate_phone_number(self, value):
        if not value.isdigit():
            raise serializers.ValidationError("Phone number must contain digits only.")
        if len(value) < 10 or len(value) > 15:
            raise serializers.ValidationError("Phone number must be between 10 and 15 digits.")
        if User.objects.filter(phone_number=value).exists():
            raise serializers.ValidationError("Phone number is already registered.")
        return value

    def validate_first_name(self, value):
        if not value.isalpha():
            raise serializers.ValidationError("First name must contain letters only.")
        if len(value) < 2:
            raise serializers.ValidationError("First name must be at least 2 characters long.")
        return value

    def validate_last_name(self, value):
        if not value.isalpha():
            raise serializers.ValidationError("Last name must contain letters only.")
        if len(value) < 2:
            raise serializers.ValidationError("Last name must be at least 2 characters long.")
        return value

    def validate_password(self, value):
        if len(value) < 8:
            raise serializers.ValidationError("Password must be at least 8 characters long.")
        if not any(char.isdigit() for char in value):
            raise serializers.ValidationError("Password must contain at least one number.")
        if not any(char.isalpha() for char in value):
            raise serializers.ValidationError("Password must contain at least one letter.")
        return value

    def create(self, validated_data):
        required_fields = ['email', 'phone_number', 'first_name', 'last_name', 'national_id', 'password']
        for field in required_fields:
            if field not in validated_data:
                raise serializers.ValidationError({field: f"{field.replace('_', ' ').capitalize()} is required."})
        user = User.objects.create_user(
            email=validated_data['email'],
            phone_number=validated_data['phone_number'],
            first_name=validated_data['first_name'],
            last_name=validated_data['last_name'],
            national_id=validated_data['national_id'],
            password=validated_data['password']
        )
        return user

class RoleSerializer(serializers.ModelSerializer):
    class Meta:
        model = Role
        fields = '__all__'

class UserRoleSerializer(serializers.ModelSerializer):
    class Meta:
        model = UserRole
        fields = '__all__'
