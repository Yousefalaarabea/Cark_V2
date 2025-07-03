from django.contrib import admin
from .models import Notification


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ['title', 'receiver', 'sender', 'notification_type', 'priority', 'is_read', 'created_at']
    list_filter = ['notification_type', 'priority', 'is_read', 'created_at']
    search_fields = ['title', 'message', 'receiver__email', 'sender__email']
    ordering = ['-created_at']
    
    fieldsets = (
        ('معلومات الإشعار', {
            'fields': ('title', 'message', 'notification_type', 'priority', 'data')
        }),
        ('المرسل والمستقبل', {
            'fields': ('sender', 'receiver')
        }),
        ('حالة الإشعار', {
            'fields': ('is_read', 'read_at')
        }),
        ('التواريخ', {
            'fields': ('created_at',),
            'classes': ('collapse',)
        }),
    )
    
    readonly_fields = ['created_at', 'read_at']
    
    actions = ['mark_as_read', 'mark_as_unread']
    
    def mark_as_read(self, request, queryset):
        """تمييز الإشعارات المحددة كمقروءة"""
        from django.utils import timezone
        count = queryset.update(is_read=True, read_at=timezone.now())
        self.message_user(request, f'تم تمييز {count} إشعار كمقروء')
    mark_as_read.short_description = "تمييز كمقروء"
    
    def mark_as_unread(self, request, queryset):
        """تمييز الإشعارات المحددة كغير مقروءة"""
        count = queryset.update(is_read=False, read_at=None)
        self.message_user(request, f'تم تمييز {count} إشعار كغير مقروء')
    mark_as_unread.short_description = "تمييز كغير مقروء"
