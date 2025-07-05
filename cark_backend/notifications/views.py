from django.shortcuts import render
from rest_framework import viewsets, permissions
from rest_framework.decorators import action
from rest_framework.response import Response
from django.contrib.auth import get_user_model
from .models import Notification
from .serializers import NotificationSerializer, NotificationCreateSerializer
from .services import NotificationService

User = get_user_model()


class NotificationViewSet(viewsets.ModelViewSet):
    """إدارة الإشعارات"""
    serializer_class = NotificationSerializer
    permission_classes = [permissions.IsAuthenticated]
    
    def get_queryset(self):
        """الحصول على إشعارات المستخدم الحالي فقط"""
        return Notification.objects.filter(receiver=self.request.user)  # type: ignore
    
    def get_serializer_class(self):
        """اختيار الـ serializer المناسب"""
        if self.action == 'create':
            return NotificationCreateSerializer
        return NotificationSerializer
    
    def list(self, request, *args, **kwargs):
        """الحصول على جميع الإشعارات مع معلومات العدد"""
        queryset = self.get_queryset()
        
        # حساب الإحصائيات
        total_count = queryset.count()
        unread_count = queryset.filter(is_read=False).count()
        read_count = queryset.filter(is_read=True).count()
        
        # بدون pagination - جلب جميع الإشعارات
        serializer = self.get_serializer(queryset, many=True)
        return Response({
            'results': serializer.data,
            'total_count': total_count,
            'unread_count': unread_count,
            'read_count': read_count,
            'stats': {
                'by_type': {
                    'rental': queryset.filter(notification_type='RENTAL').count(),
                    'payment': queryset.filter(notification_type='PAYMENT').count(),
                    'system': queryset.filter(notification_type='SYSTEM').count(),
                    'promotion': queryset.filter(notification_type='PROMOTION').count(),
                    'other': queryset.filter(notification_type='OTHER').count(),
                },
                'by_priority': {
                    'urgent': queryset.filter(priority='URGENT').count(),
                    'high': queryset.filter(priority='HIGH').count(),
                    'normal': queryset.filter(priority='NORMAL').count(),
                    'low': queryset.filter(priority='LOW').count(),
                }
            }
        })
    
    @action(detail=False, methods=['get'])
    def unread(self, request):
        """الحصول على الإشعارات غير المقروءة مع العدد"""
        notifications = self.get_queryset().filter(is_read=False)
        count = notifications.count()
        
        # Pagination
        page = self.paginate_queryset(notifications)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            response = self.get_paginated_response(serializer.data)
            response.data['unread_count'] = count
            return response
        
        serializer = self.get_serializer(notifications, many=True)
        return Response({
            'results': serializer.data,
            'unread_count': count
        })
    
    @action(detail=False, methods=['get'])
    def count(self, request):
        """عدد الإشعارات غير المقروءة"""
        unread_count = self.get_queryset().filter(is_read=False).count()
        total_count = self.get_queryset().count()
        return Response({
            'unread_count': unread_count,
            'total_count': total_count
        })
    
    @action(detail=False, methods=['get'])
    def sent(self, request):
        """الإشعارات المرسلة من المستخدم"""
        sent_notifications = Notification.objects.filter(sender=request.user)  # type: ignore
        page = self.paginate_queryset(sent_notifications)
        
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        
        serializer = self.get_serializer(sent_notifications, many=True)
        return Response(serializer.data)
    
    @action(detail=False, methods=['get'])
    def stats(self, request):
        """إحصائيات الإشعارات"""
        user_notifications = self.get_queryset()
        
        stats = {
            'total': user_notifications.count(),
            'unread': user_notifications.filter(is_read=False).count(),
            'read': user_notifications.filter(is_read=True).count(),
            'by_type': {
                'rental': user_notifications.filter(notification_type='RENTAL').count(),
                'payment': user_notifications.filter(notification_type='PAYMENT').count(),
                'system': user_notifications.filter(notification_type='SYSTEM').count(),
                'promotion': user_notifications.filter(notification_type='PROMOTION').count(),
                'other': user_notifications.filter(notification_type='OTHER').count(),
            },
            'by_priority': {
                'urgent': user_notifications.filter(priority='URGENT').count(),
                'high': user_notifications.filter(priority='HIGH').count(),
                'normal': user_notifications.filter(priority='NORMAL').count(),
                'low': user_notifications.filter(priority='LOW').count(),
            }
        }
        
        return Response(stats)
    
    @action(detail=True, methods=['post'])
    def mark_as_read(self, request, pk=None):
        """تمييز إشعار كمقروء"""
        notification = self.get_object()
        notification.mark_as_read()
        return Response({
            'status': 'marked as read',
            'notification': self.get_serializer(notification).data
        })
    
    @action(detail=False, methods=['post'])
    def mark_all_as_read(self, request):
        """تمييز جميع الإشعارات كمقروءة"""
        from django.utils import timezone
        
        unread_notifications = self.get_queryset().filter(is_read=False)
        count = unread_notifications.count()
        
        unread_notifications.update(
            is_read=True, 
            read_at=timezone.now()
        )
        
        return Response({
            'status': f'marked {count} notifications as read',
            'count': count
        })
    
    @action(detail=False, methods=['delete'])
    def delete_read(self, request):
        """حذف جميع الإشعارات المقروءة"""
        read_notifications = self.get_queryset().filter(is_read=True)
        count = read_notifications.count()
        read_notifications.delete()
        
        return Response({
            'status': f'deleted {count} read notifications',
            'count': count
        })
    
    @action(detail=False, methods=['post'])
    def test_booking_notification(self, request):
        """Test endpoint to create a sample booking notification"""
        try:
            # Get the current user
            user = request.user
            
            # Create a test notification
            notification = Notification.objects.create( # type: ignore
                sender=user,
                receiver=user,  # Send to self for testing
                title="Test Booking Request",
                message="This is a test booking request notification",
                notification_type="RENTAL",
                priority="HIGH",
                data={
                    "renterId": user.id,
                    "carId": 1,
                    "status": "PendingOwnerConfirmation",
                    "rentalId": 1,
                    "startDate": "2024-01-01T10:00:00Z",
                    "endDate": "2024-01-03T10:00:00Z",
                    "pickupAddress": "Cairo, Egypt",
                    "dropoffAddress": "Alexandria, Egypt",
                    "renterName": f"{user.first_name} {user.last_name}",
                    "carName": "Toyota Camry",
                    "dailyPrice": 200.0,
                    "totalDays": 3,
                    "totalAmount": 600.0,
                    "depositAmount": 90.0,
                },
                is_read=False
            )
            
            return Response({
                'status': 'Test notification created successfully',
                'notification': NotificationSerializer(notification).data
            })
            
        except Exception as e:
            return Response({
                'error': str(e)
            }, status=500)
