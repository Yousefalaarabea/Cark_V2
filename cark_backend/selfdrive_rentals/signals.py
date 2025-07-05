from django.db.models.signals import post_save
from django.dispatch import receiver
from .models import SelfDriveRental, SelfDriveRentalStatusHistory
from notifications.services import NotificationService

# Commented out to avoid duplicate notifications
# @receiver(post_save, sender=SelfDriveRental)
# def send_booking_request_notification(sender, instance, created, **kwargs):
#     """
#     Send notification to car owner when a new self-drive rental is created
#     """
#     if created:
#         # Send booking request notification to car owner
#         NotificationService.send_booking_request_notification(instance)

# Commented out to avoid duplicate notifications
# @receiver(post_save, sender=SelfDriveRentalStatusHistory)
# def send_status_update_notification(sender, instance, created, **kwargs):
#     """
#     Send notification when rental status changes
#     """
#     if created:
#         # Send status update notification
#         NotificationService.send_rental_status_update_notification(
#             rental=instance.rental,
#             old_status=instance.old_status,
#             new_status=instance.new_status,
#             updated_by=instance.changed_by
#         ) 