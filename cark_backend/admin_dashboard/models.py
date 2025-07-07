from django.db import models
from django.conf import settings
from cars.models import Car
from documents.models import Document
from users.models import User as CustomUser
from rentals.models import Rental
from selfdrive_rentals.models import SelfDriveRental
from feedback.models import Rating
from notifications.models import Notification


class AdminVerification(models.Model):
    """نموذج لتتبع عمليات التحقق الإدارية"""
    
    VERIFICATION_TYPES = [
        ('car', 'سيارة'),
        ('document', 'مستند'),
        ('user', 'مستخدم'),
        ('rental', 'رحلة'),
        ('report', 'بلاغ'),
    ]
    
    STATUS_CHOICES = [
        ('pending', 'معلق'),
        ('approved', 'موافق'),
        ('rejected', 'مرفوض'),
        ('partially_approved', 'موافق جزئياً'),
    ]
    
    verification_type = models.CharField(max_length=20, choices=VERIFICATION_TYPES)
    target_id = models.IntegerField()  # ID للعنصر المراد التحقق منه
    admin_user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='admin_verifications')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    notes = models.TextField(blank=True, null=True)
    rejection_reason = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        unique_together = ['verification_type', 'target_id']
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.get_verification_type_display()} - {self.target_id}"


class DocumentVerification(models.Model):
    """نموذج خاص بتحقق المستندات"""
    
    document = models.ForeignKey(Document, on_delete=models.CASCADE, related_name='admin_verifications')
    admin_user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='document_verifications')
    status = models.CharField(max_length=20, choices=AdminVerification.STATUS_CHOICES, default='pending')
    notes = models.TextField(blank=True, null=True)
    rejection_reason = models.TextField(blank=True, null=True)
    verified_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        unique_together = ['document', 'admin_user']
        ordering = ['-verified_at']
    
    def __str__(self):
        return f"تحقق {self.document} - {self.admin_user.username}"


class CarVerification(models.Model):
    """نموذج خاص بتحقق السيارات"""
    
    car = models.ForeignKey(Car, on_delete=models.CASCADE, related_name='verifications')
    admin_user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='car_verifications')
    status = models.CharField(max_length=20, choices=AdminVerification.STATUS_CHOICES, default='pending')
    notes = models.TextField(blank=True, null=True)
    rejection_reason = models.TextField(blank=True, null=True)
    verified_at = models.DateTimeField(auto_now=True)
    
    # تفاصيل إضافية للسيارة
    documents_verified = models.BooleanField(default=False)
    images_verified = models.BooleanField(default=False)
    pricing_verified = models.BooleanField(default=False)
    
    class Meta:
        unique_together = ['car', 'admin_user']
        ordering = ['-verified_at']
    
    def __str__(self):
        return f"تحقق {self.car} - {self.admin_user.username}"


class AdminAction(models.Model):
    """نموذج لتتبع جميع الإجراءات الإدارية"""
    
    ACTION_TYPES = [
        ('approve_car', 'موافقة على سيارة'),
        ('reject_car', 'رفض سيارة'),
        ('approve_document', 'موافقة على مستند'),
        ('reject_document', 'رفض مستند'),
        ('suspend_user', 'حظر مستخدم'),
        ('activate_user', 'تفعيل مستخدم'),
        ('cancel_rental', 'إلغاء رحلة'),
        ('resolve_report', 'حل بلاغ'),
        ('delete_rating', 'حذف تقييم'),
    ]
    
    admin_user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='admin_actions')
    action_type = models.CharField(max_length=30, choices=ACTION_TYPES)
    target_type = models.CharField(max_length=20)
    target_id = models.IntegerField()
    details = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.get_action_type_display()} - {self.admin_user.username}"


class SystemAlert(models.Model):
    """نموذج للتنبيهات النظامية"""
    
    ALERT_TYPES = [
        ('expiring_document', 'مستند منتهي الصلاحية'),
        ('high_priority_report', 'بلاغ عالي الأولوية'),
        ('suspicious_activity', 'نشاط مشبوه'),
        ('system_error', 'خطأ في النظام'),
        ('payment_issue', 'مشكلة في الدفع'),
    ]
    
    SEVERITY_CHOICES = [
        ('low', 'منخفض'),
        ('medium', 'متوسط'),
        ('high', 'عالي'),
        ('critical', 'حرج'),
    ]
    
    alert_type = models.CharField(max_length=30, choices=ALERT_TYPES)
    severity = models.CharField(max_length=10, choices=SEVERITY_CHOICES, default='medium')
    title = models.CharField(max_length=200)
    message = models.TextField()
    target_type = models.CharField(max_length=20, blank=True, null=True)
    target_id = models.IntegerField(blank=True, null=True)
    is_resolved = models.BooleanField(default=False)
    resolved_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, blank=True, null=True)
    resolved_at = models.DateTimeField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.title} - {self.get_severity_display()}" 