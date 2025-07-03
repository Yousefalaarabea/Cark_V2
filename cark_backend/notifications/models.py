from django.db import models

# Create your models here.
from django.db import models
from django.contrib.auth import get_user_model
import uuid

User = get_user_model()

class Notification(models.Model):
    PRIORITY_CHOICES = [
        ('LOW', 'منخفضة'),
        ('NORMAL', 'عادية'),
        ('HIGH', 'عالية'),
        ('URGENT', 'عاجلة'),
    ]
    
    TYPE_CHOICES = [
        ('RENTAL', 'حجز'),
        ('PAYMENT', 'دفع'),
        ('SYSTEM', 'نظام'),
        ('PROMOTION', 'ترويجي'),
        ('OTHER', 'أخرى'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    sender = models.ForeignKey(User, on_delete=models.CASCADE, related_name='sent_notifications', null=True, blank=True)
    receiver = models.ForeignKey(User, on_delete=models.CASCADE, related_name='received_notifications')
    title = models.CharField(max_length=200)
    message = models.TextField()
    notification_type = models.CharField(max_length=20, choices=TYPE_CHOICES, default='OTHER')
    priority = models.CharField(max_length=10, choices=PRIORITY_CHOICES, default='NORMAL')
    data = models.JSONField(default=dict, blank=True)  # type: ignore
    is_read = models.BooleanField(default=False)  # type: ignore
    read_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['-created_at']
        verbose_name = "إشعار"
        verbose_name_plural = "الإشعارات"
    
    def mark_as_read(self):
        """تمييز الإشعار كمقروء"""
        from django.utils import timezone
        if not self.is_read:
            self.is_read = True
            self.read_at = timezone.now()
            self.save(update_fields=['is_read', 'read_at'])
    
    def __str__(self):
        return f"{self.title} - {self.receiver.email}"  # type: ignore