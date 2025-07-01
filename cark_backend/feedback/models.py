from django.db import models
from django.contrib.auth import get_user_model
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from rentals.models import Rental
from selfdrive_rentals.models import SelfDriveRental
from users.models import UserRole

User = get_user_model()

class Rating(models.Model):
    reviewer = models.ForeignKey(User, on_delete=models.CASCADE, related_name='given_ratings')
    # reviewee can be Car or UserRole
    reviewee_content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE)
    reviewee_object_id = models.PositiveIntegerField()
    reviewee = GenericForeignKey('reviewee_content_type', 'reviewee_object_id')
    rental_content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE, related_name='rental_type')
    rental_object_id = models.PositiveIntegerField()
    rental = GenericForeignKey('rental_content_type', 'rental_object_id')
    rating = models.PositiveSmallIntegerField(choices=[(i, i) for i in range(1, 6)])
    notes = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('reviewer', 'rental_content_type', 'rental_object_id', 'reviewee_content_type', 'reviewee_object_id')

class Report(models.Model):
    REPORT_TARGET_CHOICES = [
        ('car', 'Car'),
        ('user', 'User'),
    ]
    REPORT_REASON_CHOICES = [
        ('معلومات مضللة', 'معلومات مضللة'),
        ('تأخير كبير', 'تأخير كبير'),
        ('سلوك غير لائق', 'سلوك غير لائق'),
        ('أخرى', 'أخرى'),
    ]
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('under_review', 'Under Review'),
        ('resolved', 'Resolved'),
    ]
    reporter = models.ForeignKey(User, on_delete=models.CASCADE, related_name='reports_made')
    target_type = models.CharField(max_length=10, choices=REPORT_TARGET_CHOICES)
    target_content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE)
    target_object_id = models.PositiveIntegerField()
    target = GenericForeignKey('target_content_type', 'target_object_id')
    reason = models.CharField(max_length=50, choices=REPORT_REASON_CHOICES)
    details = models.TextField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    created_at = models.DateTimeField(auto_now_add=True)
