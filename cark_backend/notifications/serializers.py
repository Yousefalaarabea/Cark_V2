from rest_framework import serializers
from .models import Notification


class NotificationSerializer(serializers.ModelSerializer):
    sender_email = serializers.CharField(source='sender.email', read_only=True, allow_null=True)
    receiver_email = serializers.CharField(source='receiver.email', read_only=True)
    priority_display = serializers.CharField(source='get_priority_display', read_only=True)
    type_display = serializers.CharField(source='get_notification_type_display', read_only=True)
    time_ago = serializers.SerializerMethodField()
    
    class Meta:
        model = Notification
        fields = ['id', 'sender', 'sender_email', 'receiver', 'receiver_email', 
                 'title', 'message', 'notification_type', 'type_display', 
                 'priority', 'priority_display', 'data', 'is_read', 'read_at', 
                 'created_at', 'time_ago']
        read_only_fields = ['id', 'sender', 'receiver', 'read_at', 'created_at']
    
    def get_time_ago(self, obj):
        """حساب الوقت منذ الإنشاء"""
        from django.utils import timezone
        from datetime import timedelta
        
        now = timezone.now()
        diff = now - obj.created_at
        
        if diff.days > 0:
            return f"منذ {diff.days} يوم"
        elif diff.seconds > 3600:
            hours = diff.seconds // 3600
            return f"منذ {hours} ساعة"
        elif diff.seconds > 60:
            minutes = diff.seconds // 60
            return f"منذ {minutes} دقيقة"
        else:
            return "منذ قليل"


class NotificationCreateSerializer(serializers.ModelSerializer):
    """سيريالايزر لإنشاء إشعار جديد"""
    
    class Meta:
        model = Notification
        fields = ['receiver', 'title', 'message', 'notification_type', 'priority', 'data']
    
    def create(self, validated_data):
        """إنشاء إشعار جديد"""
        request = self.context.get('request')
        if request and request.user.is_authenticated:
            validated_data['sender'] = request.user
        return super().create(validated_data) 