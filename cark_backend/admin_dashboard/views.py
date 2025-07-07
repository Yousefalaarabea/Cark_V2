from rest_framework import viewsets, status, permissions
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.authentication import SessionAuthentication, BasicAuthentication
from django.shortcuts import get_object_or_404
from django.db.models import Q, Count, Avg, Sum
from django.utils import timezone
from datetime import timedelta
from django.contrib.auth.models import User
from django.db import transaction
from django.conf import settings
from django.contrib.auth import get_user_model

from .models import AdminVerification, AdminAction, SystemAlert
from documents.models import DocumentVerification
from cars.models import Car
from documents.models import Document
from .serializers import (
    CarDetailSerializer, DocumentDetailSerializer, UserDetailSerializer,
    RentalDetailSerializer, SelfDriveRentalDetailSerializer, RatingDetailSerializer,
    AdminVerificationSerializer, DocumentVerificationSerializer, CarVerificationSerializer,
    AdminActionSerializer, SystemAlertSerializer, DashboardStatsSerializer
)
from users.models import User as CustomUser
from rentals.models import Rental
from selfdrive_rentals.models import SelfDriveRental
from feedback.models import Rating
from notifications.models import Notification


class IsAdminUser(permissions.BasePermission):
    """صلاحية للتحقق من أن المستخدم مشرف"""
    
    def has_permission(self, request, view):
        # السماح للجميع في التطوير
        if settings.DEBUG:
            return True
        return request.user.is_authenticated and (
            request.user.is_staff or request.user.is_superuser
        )


class AdminDashboardView(APIView):
    """لوحة التحكم الرئيسية للإدارة"""
    permission_classes = [IsAdminUser]
    authentication_classes = [SessionAuthentication, BasicAuthentication]
    
    def get(self, request):
        """الحصول على إحصائيات لوحة التحكم"""
        
        # إحصائيات عامة
        total_users = CustomUser.objects.count()
        total_cars = Car.objects.count()
        total_rentals = Rental.objects.count() + SelfDriveRental.objects.count()
        
        # السيارات المعلقة
        pending_cars = Car.objects.filter(approval_status=False).count()
        
        # المستندات المعلقة
        pending_documents = Document.objects.filter(status='pending').count()
        
        # الرحلات النشطة
        active_rentals = Rental.objects.filter(status='active').count() + \
                        SelfDriveRental.objects.filter(status='active').count()
        
        # المستندات المنتهية الصلاحية قريباً
        expiring_documents = Document.objects.filter(
            expiry_date__lte=timezone.now().date() + timedelta(days=30)
        ).count()
        
        # إجمالي الإيرادات (مثال)
        total_revenue = 100000  # يمكن حسابها من جدول المدفوعات
        
        # متوسط التقييم
        avg_rating = Rating.objects.aggregate(avg=Avg('rating'))['avg'] or 0
        
        stats = {
            'total_users': total_users,
            'total_cars': total_cars,
            'total_rentals': total_rentals,
            'pending_cars': pending_cars,
            'pending_documents': pending_documents,
            'active_rentals': active_rentals,
            'expiring_documents': expiring_documents,
            'total_revenue': total_revenue,
            'avg_rating': round(avg_rating, 2)
        }
        
        return Response(stats)


class AdminCarViewSet(viewsets.ModelViewSet):
    """إدارة السيارات للمشرفين"""
    permission_classes = [IsAdminUser]
    authentication_classes = [SessionAuthentication, BasicAuthentication]
    serializer_class = CarDetailSerializer
    queryset = Car.objects.all()
    
    def get_queryset(self):
        """فلترة السيارات حسب المعايير"""
        queryset = Car.objects.select_related('owner').order_by('-created_at')
        
        # فلترة حسب الحالة
        status_filter = self.request.query_params.get('approval_status', None)
        if status_filter:
            if status_filter == 'False':
                queryset = queryset.filter(approval_status=False)
            elif status_filter == 'True':
                queryset = queryset.filter(approval_status=True)
        
        # فلترة حسب الماركة
        brand_filter = self.request.query_params.get('brand', None)
        if brand_filter:
            queryset = queryset.filter(brand__icontains=brand_filter)
        
        # فلترة حسب المالك
        owner_filter = self.request.query_params.get('owner', None)
        if owner_filter:
            queryset = queryset.filter(owner__full_name__icontains=owner_filter)
        
        return queryset
    
    @action(detail=True, methods=['post'])
    def approve(self, request, pk=None):
        """الموافقة على سيارة"""
        car = self.get_object()
        admin_user = request.user
        if not admin_user.is_authenticated and settings.DEBUG:
            User = get_user_model()
            admin_user = User.objects.filter(is_superuser=True).first()
        with transaction.atomic():
            car.approval_status = True
            car.save()
            # CarVerification.objects.create(
            #     car=car,
            #     verification_type='Admin',
            #     status='Approved',
            #     comments=request.data.get('notes', ''),
            #     verified_by=admin_user
            # )
            AdminAction.objects.create(
                admin_user=admin_user,
                action_type='approve_car',
                target_type='car',
                target_id=car.id,
                details={'notes': request.data.get('notes', '')}
            )
            Notification.objects.create(
                receiver=car.owner,
                title="🚗 Car Approved!",
                message=f"Congratulations! Your car {car.brand} {car.model} has been approved and is now available for rentals. 🎉",
                notification_type='car_approved'
            )
        return Response({'message': 'تمت الموافقة على السيارة بنجاح'})
    
    @action(detail=True, methods=['post'])
    def reject(self, request, pk=None):
        """رفض سيارة"""
        car = self.get_object()
        rejection_reason = request.data.get('rejection_reason', '')
        admin_user = request.user
        if not admin_user.is_authenticated and settings.DEBUG:
            User = get_user_model()
            admin_user = User.objects.filter(is_superuser=True).first()
        if not rejection_reason:
            return Response(
                {'error': 'يجب تحديد سبب الرفض'}, 
                status=status.HTTP_400_BAD_REQUEST
            )
        with transaction.atomic():
            car.approval_status = False
            car.save()
            # CarVerification.objects.create(
            #     car=car,
            #     verification_type='Admin',
            #     status='Rejected',
            #     comments=rejection_reason,
            #     verified_by=admin_user
            # )
            AdminAction.objects.create(
                admin_user=admin_user,
                action_type='reject_car',
                target_type='car',
                target_id=car.id,
                details={'rejection_reason': rejection_reason}
            )
            Notification.objects.create(
                receiver=car.owner,
                title="🚗 Car Rejected!",
                message=f"Unfortunately, your car {car.brand} {car.model} has been rejected. The reason: {rejection_reason}",
                notification_type='car_rejected'
            )
        return Response({'message': 'تم رفض السيارة بنجاح'})
    
    @action(detail=True, methods=['post'])
    def partial_approval(self, request, pk=None):
        """الموافقة الجزئية على سيارة"""
        car = self.get_object()
        
        # التحقق من الأجزاء المعتمدة
        documents_verified = request.data.get('documents_verified', False)
        images_verified = request.data.get('images_verified', False)
        pricing_verified = request.data.get('pricing_verified', False)
        notes = request.data.get('notes', '')
        
        with transaction.atomic():
            # إنشاء سجل التحقق الجزئي
            # CarVerification.objects.create(
            #     car=car,
            #     verification_type='Admin',
            #     status='Partially Approved',
            #     comments=notes,
            #     documents_verified=documents_verified,
            #     images_verified=images_verified,
            #     pricing_verified=pricing_verified
            # )
            
            # إنشاء سجل الإجراء
            AdminAction.objects.create(
                admin_user=request.user,
                action_type='approve_car',
                target_type='car',
                target_id=car.id,
                details={
                    'partial_approval': True,
                    'documents_verified': documents_verified,
                    'images_verified': images_verified,
                    'pricing_verified': pricing_verified,
                    'notes': notes
                }
            )
        
        return Response({'message': 'تمت الموافقة الجزئية بنجاح'})


class AdminDocumentViewSet(viewsets.ModelViewSet):
    """إدارة المستندات للمشرفين"""
    permission_classes = [IsAdminUser]
    authentication_classes = [SessionAuthentication, BasicAuthentication]
    serializer_class = DocumentDetailSerializer
    queryset = Document.objects.all()
    
    def get_queryset(self):
        """فلترة المستندات حسب المعايير"""
        queryset = Document.objects.select_related('user', 'document_type', 'car')
        
        # فلترة حسب الحالة
        status_filter = self.request.query_params.get('status', None)
        if status_filter:
            queryset = queryset.filter(status__iexact=status_filter)
        
        # فلترة حسب النوع (اسم النوع)
        type_filter = self.request.query_params.get('type', None)
        if type_filter:
            queryset = queryset.filter(document_type__name__icontains=type_filter)
        
        # فلترة حسب المستخدم (اسم المستخدم)
        user_filter = self.request.query_params.get('user', None)
        if user_filter:
            queryset = queryset.filter(user__full_name__icontains=user_filter)
        
        # فلترة المستندات المنتهية الصلاحية
        expiring = self.request.query_params.get('expiring', None)
        if expiring == 'true':
            queryset = queryset.filter(
                expiry_date__lte=timezone.now().date() + timedelta(days=30)
            )
        
        return queryset
    
    @action(detail=True, methods=['post'])
    def approve(self, request, pk=None):
        """الموافقة على مستند"""
        document = self.get_object()
        admin_user = request.user
        if not admin_user.is_authenticated and settings.DEBUG:
            User = get_user_model()
            admin_user = User.objects.filter(is_superuser=True).first()
        with transaction.atomic():
            # البحث عن تحقق موجود أو إنشاء واحد جديد
            verification, created = DocumentVerification.objects.get_or_create(
                document=document,
                verification_type='Admin',
                defaults={
                    'status': 'Approved',
                    'comments': request.data.get('notes', ''),
                    'verified_by': admin_user
                }
            )
            # إذا كان التحقق موجود بالفعل، قم بتحديثه
            if not created:
                verification.status = 'Approved'
                verification.comments = request.data.get('notes', '')
                verification.verified_by = admin_user
                verification.save()
            
            # تحديث حالة المستند يدوياً
            document.status = 'Approved'
            document.save()
            
            AdminAction.objects.create(
                admin_user=admin_user,
                action_type='approve_document',
                target_type='document',
                target_id=document.id,
                details={'notes': request.data.get('notes', '')}
            )
            # إنشاء إشعار فقط إذا كان المستند مرتبط بمستخدم
            if document.user:
                Notification.objects.create(
                    receiver=document.user,
                    title="🚗 Document Approved!",
                    message=f"Congratulations! Your document {document.document_type} has been approved and is now available for rentals. 🎉",
                    notification_type='document_approved'
                )
        return Response({'message': 'تمت الموافقة على المستند بنجاح'})
    
    @action(detail=True, methods=['post'])
    def reject(self, request, pk=None):
        """رفض مستند"""
        document = self.get_object()
        rejection_reason = request.data.get('rejection_reason', '')
        admin_user = request.user
        if not admin_user.is_authenticated and settings.DEBUG:
            User = get_user_model()
            admin_user = User.objects.filter(is_superuser=True).first()
        if not rejection_reason:
            return Response(
                {'error': 'يجب تحديد سبب الرفض'}, 
                status=status.HTTP_400_BAD_REQUEST
            )
        with transaction.atomic():
            # البحث عن تحقق موجود أو إنشاء واحد جديد
            verification, created = DocumentVerification.objects.get_or_create(
                document=document,
                verification_type='Admin',
                defaults={
                    'status': 'Rejected',
                    'comments': rejection_reason,
                    'verified_by': admin_user
                }
            )
            # إذا كان التحقق موجود بالفعل، قم بتحديثه
            if not created:
                verification.status = 'Rejected'
                verification.comments = rejection_reason
                verification.verified_by = admin_user
                verification.save()
            
            # تحديث حالة المستند يدوياً
            document.status = 'Rejected'
            document.save()
            
            AdminAction.objects.create(
                admin_user=admin_user,
                action_type='reject_document',
                target_type='document',
                target_id=document.id,
                details={'rejection_reason': rejection_reason}
            )
            # إنشاء إشعار فقط إذا كان المستند مرتبط بمستخدم
            if document.user:
                Notification.objects.create(
                    receiver=document.user,
                    title="🚗 Document Rejected!",
                    message=f"Unfortunately, your document {document.document_type} has been rejected. The reason: {rejection_reason}",
                    notification_type='document_rejected'
                )
        return Response({'message': 'تم رفض المستند بنجاح'})


class AdminUserViewSet(viewsets.ModelViewSet):
    """إدارة المستخدمين للمشرفين"""
    permission_classes = [IsAdminUser]
    authentication_classes = [SessionAuthentication, BasicAuthentication]
    serializer_class = UserDetailSerializer
    queryset = CustomUser.objects.all()
    
    def get_queryset(self):
        """فلترة المستخدمين حسب المعايير"""
        queryset = CustomUser.objects.annotate(
            cars_count=Count('cars'),
            rentals_count=Count('rentals') + Count('selfdrive_rentals')
        ).order_by('-date_joined')
        
        # فلترة حسب الحالة
        status_filter = self.request.query_params.get('status', None)
        if status_filter:
            queryset = queryset.filter(status=status_filter)
        
        # فلترة حسب الاسم
        name_filter = self.request.query_params.get('name', None)
        if name_filter:
            queryset = queryset.filter(full_name__icontains=name_filter)
        
        # فلترة حسب التقييم
        min_rating = self.request.query_params.get('min_rating', None)
        if min_rating:
            queryset = queryset.filter(avg_rating__gte=float(min_rating))
        
        return queryset
    
    @action(detail=True, methods=['post'])
    def suspend(self, request, pk=None):
        """حظر مستخدم"""
        user = self.get_object()
        reason = request.data.get('reason', '')
        
        with transaction.atomic():
            # تغيير حالة المستخدم
            user.status = 'suspended'
            user.save()
            
            # إنشاء سجل الإجراء
            AdminAction.objects.create(
                admin_user=request.user,
                action_type='suspend_user',
                target_type='user',
                target_id=user.id,
                details={'reason': reason}
            )
            
            # إرسال إشعار للمستخدم
            Notification.objects.create(
                receiver=user,
                title="🚗 Account Suspended!",
                message=f"Unfortunately, your account has been suspended. The reason: {reason}",
                notification_type='account_suspended'
            )
        
        return Response({'message': 'تم حظر المستخدم بنجاح'})
    
    @action(detail=True, methods=['post'])
    def activate(self, request, pk=None):
        """تفعيل مستخدم"""
        user = self.get_object()
        
        with transaction.atomic():
            # تغيير حالة المستخدم
            user.status = 'active'
            user.save()
            
            # إنشاء سجل الإجراء
            AdminAction.objects.create(
                admin_user=request.user,
                action_type='activate_user',
                target_type='user',
                target_id=user.id
            )
            
            # إرسال إشعار للمستخدم
            Notification.objects.create(
                receiver=user,
                title="🚗 Account Activated!",
                message="Congratulations! Your account has been activated successfully!",
                notification_type='account_activated'
            )
        
        return Response({'message': 'تم تفعيل المستخدم بنجاح'})


class AdminRentalViewSet(viewsets.ModelViewSet):
    """إدارة الرحلات للمشرفين"""
    permission_classes = [IsAdminUser]
    authentication_classes = [SessionAuthentication, BasicAuthentication]
    serializer_class = RentalDetailSerializer
    queryset = Rental.objects.all()
    
    def get_queryset(self):
        """فلترة الرحلات حسب المعايير"""
        queryset = Rental.objects.select_related('car', 'renter', 'car__owner').order_by('-created_at')
        
        # فلترة حسب الحالة
        status_filter = self.request.query_params.get('status', None)
        if status_filter:
            queryset = queryset.filter(status=status_filter)
        
        # فلترة حسب التاريخ
        date_filter = self.request.query_params.get('date', None)
        if date_filter:
            queryset = queryset.filter(start_date__date=date_filter)
        
        return queryset
    
    @action(detail=True, methods=['post'])
    def cancel(self, request, pk=None):
        """إلغاء رحلة"""
        rental = self.get_object()
        reason = request.data.get('reason', '')
        
        with transaction.atomic():
            # تغيير حالة الرحلة
            rental.status = 'cancelled'
            rental.save()
            
            # إنشاء سجل الإجراء
            AdminAction.objects.create(
                admin_user=request.user,
                action_type='cancel_rental',
                target_type='rental',
                target_id=rental.id,
                details={'reason': reason}
            )
            
            # إرسال إشعارات للمستخدمين
            Notification.objects.create(
                receiver=rental.renter,
                title="🚗 Rental Cancelled!",
                message=f"Unfortunately, your rental has been cancelled. The reason: {reason}",
                notification_type='rental_cancelled'
            )
            
            Notification.objects.create(
                receiver=rental.car.owner,
                title="🚗 Rental Cancelled!",
                message=f"Unfortunately, the rental for your car {rental.car.brand} {rental.car.model} has been cancelled. The reason: {reason}",
                notification_type='rental_cancelled'
            )
        
        return Response({'message': 'تم إلغاء الرحلة بنجاح'})


class AdminRatingViewSet(viewsets.ModelViewSet):
    """إدارة التقييمات للمشرفين"""
    permission_classes = [IsAdminUser]
    authentication_classes = [SessionAuthentication, BasicAuthentication]
    serializer_class = RatingDetailSerializer
    queryset = Rating.objects.all()
    
    def get_queryset(self):
        """فلترة التقييمات حسب المعايير"""
        queryset = Rating.objects.select_related('renter', 'car', 'car__owner')
        
        # فلترة حسب التقييم
        rating_filter = self.request.query_params.get('rating', None)
        if rating_filter:
            queryset = queryset.filter(rating=int(rating_filter))
        
        # فلترة حسب التاريخ
        date_filter = self.request.query_params.get('date', None)
        if date_filter:
            queryset = queryset.filter(created_at__date=date_filter)
        
        return queryset
    
    @action(detail=True, methods=['post'])
    def delete(self, request, pk=None):
        """حذف تقييم"""
        rating = self.get_object()
        reason = request.data.get('reason', '')
        
        with transaction.atomic():
            # إنشاء سجل الإجراء
            AdminAction.objects.create(
                admin_user=request.user,
                action_type='delete_rating',
                target_type='rating',
                target_id=rating.id,
                details={'reason': reason}
            )
            
            # حذف التقييم
            rating.delete()
        
        return Response({'message': 'تم حذف التقييم بنجاح'})


class AdminActionViewSet(viewsets.ReadOnlyModelViewSet):
    """عرض سجلات الإجراءات الإدارية"""
    permission_classes = [IsAdminUser]
    authentication_classes = [SessionAuthentication, BasicAuthentication]
    serializer_class = AdminActionSerializer
    queryset = AdminAction.objects.all()
    
    def get_queryset(self):
        """فلترة الإجراءات حسب المعايير"""
        queryset = AdminAction.objects.select_related('admin_user')
        
        # فلترة حسب نوع الإجراء
        action_type = self.request.query_params.get('action_type', None)
        if action_type:
            queryset = queryset.filter(action_type=action_type)
        
        # فلترة حسب المشرف
        admin_user = self.request.query_params.get('admin_user', None)
        if admin_user:
            queryset = queryset.filter(admin_user__username__icontains=admin_user)
        
        return queryset


class SystemAlertViewSet(viewsets.ModelViewSet):
    """إدارة التنبيهات النظامية"""
    permission_classes = [IsAdminUser]
    authentication_classes = [SessionAuthentication, BasicAuthentication]
    serializer_class = SystemAlertSerializer
    queryset = SystemAlert.objects.all()
    
    def get_queryset(self):
        """فلترة التنبيهات حسب المعايير"""
        queryset = SystemAlert.objects.select_related('resolved_by')
        
        # فلترة حسب النوع
        alert_type = self.request.query_params.get('alert_type', None)
        if alert_type:
            queryset = queryset.filter(alert_type=alert_type)
        
        # فلترة حسب الأولوية
        severity = self.request.query_params.get('severity', None)
        if severity:
            queryset = queryset.filter(severity=severity)
        
        # فلترة حسب الحالة
        resolved = self.request.query_params.get('resolved', None)
        if resolved == 'true':
            queryset = queryset.filter(is_resolved=True)
        elif resolved == 'false':
            queryset = queryset.filter(is_resolved=False)
        
        return queryset
    
    @action(detail=True, methods=['post'])
    def resolve(self, request, pk=None):
        """حل تنبيه"""
        alert = self.get_object()
        resolution_notes = request.data.get('resolution_notes', '')
        
        with transaction.atomic():
            alert.is_resolved = True
            alert.resolved_by = request.user
            alert.resolved_at = timezone.now()
            alert.save()
            
            # إنشاء سجل الإجراء
            AdminAction.objects.create(
                admin_user=request.user,
                action_type='resolve_alert',
                target_type='alert',
                target_id=alert.id,
                details={'resolution_notes': resolution_notes}
            )
        
        return Response({'message': 'تم حل التنبيه بنجاح'}) 