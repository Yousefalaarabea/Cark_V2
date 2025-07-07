from rest_framework import serializers
from .models import AdminVerification, DocumentVerification, CarVerification, AdminAction, SystemAlert
from cars.models import Car
from documents.models import Document
from users.models import User as CustomUser
from rentals.models import Rental
from selfdrive_rentals.models import SelfDriveRental
from feedback.models import Rating


class CarDetailSerializer(serializers.ModelSerializer):
    """Serializer مفصل للسيارات مع الصور والمستندات"""
    owner_name = serializers.CharField(source='owner.full_name', read_only=True)
    owner_phone = serializers.CharField(source='owner.phone', read_only=True)
    images = serializers.SerializerMethodField()
    documents = serializers.SerializerMethodField()
    verification_status = serializers.SerializerMethodField()
    
    class Meta:
        model = Car
        fields = '__all__'
    
    def get_images(self, obj):
        """الحصول على صور السيارة"""
        images = []
        if hasattr(obj, 'images'):
            for image in obj.images.all():
                images.append({
                    'id': image.id,
                    'image_url': self.context['request'].build_absolute_uri(image.image.url) if image.image else None,
                    'image_type': getattr(image, 'image_type', 'general'),
                    'uploaded_at': image.created_at
                })
        return images
    
    def get_documents(self, obj):
        """الحصول على مستندات السيارة"""
        documents = []
        if hasattr(obj, 'documents'):
            for doc in obj.documents.all():
                documents.append({
                    'id': doc.id,
                    'document_type': doc.document_type,
                    'document_url': self.context['request'].build_absolute_uri(doc.file.url) if doc.file else None,
                    'uploaded_at': doc.created_at,
                    'expiry_date': doc.expiry_date
                })
        return documents
    
    def get_verification_status(self, obj):
        """الحصول على حالة التحقق"""
        verification = obj.verifications.first()
        if verification:
            return {
                'status': verification.status,
                'notes': verification.notes,
                'rejection_reason': verification.rejection_reason,
                'verified_at': verification.verified_at
            }
        return None


class DocumentDetailSerializer(serializers.ModelSerializer):
    """Serializer مفصل للمستندات"""
    user_name = serializers.SerializerMethodField()
    user_phone = serializers.SerializerMethodField()
    car_id = serializers.SerializerMethodField()
    car_plate = serializers.SerializerMethodField()
    document_url = serializers.SerializerMethodField()
    document_type_name = serializers.CharField(source='document_type.name', read_only=True)
    verification_status = serializers.SerializerMethodField()
    days_until_expiry = serializers.SerializerMethodField()
    comments = serializers.SerializerMethodField()

    class Meta:
        model = Document
        fields = '__all__'
        extra_fields = ['user_name', 'user_phone', 'document_url', 'verification_status', 'days_until_expiry', 'document_type_name', 'car_id', 'car_plate', 'comments']

    def get_user_name(self, obj):
        return obj.user.full_name if obj.user else None

    def get_user_phone(self, obj):
        return obj.user.phone if obj.user else None

    def get_car_id(self, obj):
        return obj.car.id if obj.car else None

    def get_car_plate(self, obj):
        return obj.car.plate_number if obj.car else None

    def get_document_url(self, obj):
        if obj.file and hasattr(obj.file, 'url') and obj.file.name:
            return self.context['request'].build_absolute_uri(obj.file.url)
        return None

    def get_verification_status(self, obj):
        verification = obj.verifications.first()
        if verification:
            return {
                'status': verification.status,
                'comments': verification.comments,
                'verified_at': verification.verification_date
            }
        return None

    def get_days_until_expiry(self, obj):
        if obj.expiry_date:
            from datetime import datetime
            today = datetime.now().date()
            expiry_date = obj.expiry_date.date() if hasattr(obj.expiry_date, 'date') else obj.expiry_date
            days = (expiry_date - today).days
            return days
        return None

    def get_comments(self, obj):
        verification = obj.verifications.filter(status__in=['Rejected', 'Pending']).first()
        if verification:
            return verification.comments
        return None


class UserDetailSerializer(serializers.ModelSerializer):
    """Serializer مفصل للمستخدمين"""
    cars_count = serializers.SerializerMethodField()
    rentals_count = serializers.SerializerMethodField()
    documents_count = serializers.SerializerMethodField()
    avg_rating = serializers.FloatField(read_only=True)
    
    class Meta:
        model = CustomUser
        fields = '__all__'
    
    def get_cars_count(self, obj):
        """عدد السيارات المملوكة"""
        return obj.cars.count()
    
    def get_rentals_count(self, obj):
        """عدد الرحلات"""
        return obj.rentals.count() + obj.selfdrive_rentals.count()
    
    def get_documents_count(self, obj):
        """عدد المستندات"""
        return obj.documents.count()


class RentalDetailSerializer(serializers.ModelSerializer):
    """Serializer مفصل للرحلات"""
    car_details = CarDetailSerializer(source='car', read_only=True)
    renter_details = UserDetailSerializer(source='renter', read_only=True)
    owner_details = UserDetailSerializer(source='car.owner', read_only=True)
    
    class Meta:
        model = Rental
        fields = '__all__'


class SelfDriveRentalDetailSerializer(serializers.ModelSerializer):
    """Serializer مفصل لرحلات القيادة الذاتية"""
    car_details = CarDetailSerializer(source='car', read_only=True)
    renter_details = UserDetailSerializer(source='renter', read_only=True)
    owner_details = UserDetailSerializer(source='car.owner', read_only=True)
    
    class Meta:
        model = SelfDriveRental
        fields = '__all__'


class RatingDetailSerializer(serializers.ModelSerializer):
    """Serializer مفصل للتقييمات"""
    renter_name = serializers.CharField(source='renter.full_name', read_only=True)
    owner_name = serializers.CharField(source='car.owner.full_name', read_only=True)
    car_details = serializers.CharField(source='car.brand', read_only=True)
    
    class Meta:
        model = Rating
        fields = '__all__'


class AdminVerificationSerializer(serializers.ModelSerializer):
    """Serializer لعمليات التحقق الإدارية"""
    
    class Meta:
        model = AdminVerification
        fields = '__all__'


class DocumentVerificationSerializer(serializers.ModelSerializer):
    """Serializer لتحقق المستندات"""
    
    class Meta:
        model = DocumentVerification
        fields = '__all__'


class CarVerificationSerializer(serializers.ModelSerializer):
    """Serializer لتحقق السيارات"""
    
    class Meta:
        model = CarVerification
        fields = '__all__'


class AdminActionSerializer(serializers.ModelSerializer):
    """Serializer للإجراءات الإدارية"""
    admin_username = serializers.CharField(source='admin_user.username', read_only=True)
    
    class Meta:
        model = AdminAction
        fields = '__all__'


class SystemAlertSerializer(serializers.ModelSerializer):
    """Serializer للتنبيهات النظامية"""
    resolved_by_username = serializers.CharField(source='resolved_by.username', read_only=True)
    
    class Meta:
        model = SystemAlert
        fields = '__all__'


class DashboardStatsSerializer(serializers.Serializer):
    """Serializer لإحصائيات لوحة التحكم"""
    total_users = serializers.IntegerField()
    total_cars = serializers.IntegerField()
    total_rentals = serializers.IntegerField()
    total_reports = serializers.IntegerField()
    pending_cars = serializers.IntegerField()
    pending_documents = serializers.IntegerField()
    active_rentals = serializers.IntegerField()
    high_priority_reports = serializers.IntegerField()
    expiring_documents = serializers.IntegerField()
    total_revenue = serializers.DecimalField(max_digits=10, decimal_places=2)
    avg_rating = serializers.FloatField() 