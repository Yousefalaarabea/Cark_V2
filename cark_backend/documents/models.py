from django.db import models
from django.contrib.auth import get_user_model
from django.forms import ValidationError
from cars.models import Car  # assuming cars app
from users.models import Role  # assuming a separate Role model
from django.conf import settings

User = get_user_model()

class DocumentType(models.Model):
    name = models.CharField(max_length=50, unique=True)
    description = models.TextField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    def __str__(self):
        return self.name


class RoleDocumentRequirement(models.Model):
    role = models.ForeignKey(Role, on_delete=models.CASCADE)
    document_type = models.ForeignKey(DocumentType, on_delete=models.CASCADE)
    is_mandatory = models.BooleanField(default=True)

    def __str__(self):
        return f'{self.role.name} - {self.document_type.name}'


class Document(models.Model):
    STATUS_CHOICES = [
        ('Pending', 'Pending'),
        ('Approved', 'Approved'),
        ('Rejected', 'Rejected'),
    ]

    user = models.ForeignKey(User, on_delete=models.CASCADE, null=True, blank=True)
    car = models.ForeignKey('cars.Car', on_delete=models.CASCADE, null=True, blank=True)
    
    def document_upload_path(instance, filename):
        if instance.user:
            return f'documents/user_{instance.user.id}/{filename}'
        elif instance.car:
            return f'documents/car_{instance.car.id}/{filename}'
        return f'documents/other/{filename}'

    file = models.FileField(upload_to=document_upload_path)
    document_type = models.ForeignKey('documents.DocumentType', on_delete=models.CASCADE)
    
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='Pending')
    
    def update_status_from_verifications(self):
        verifications = self.verifications.all()
        if not verifications.exists():
            self.status = 'Pending'
        else:
            # لو في أي فرفكيشن مرفوضة -> Reject
            if verifications.filter(status='Rejected').exists():
                self.status = 'Rejected'
            # لو كلها موافق عليها -> Approve
            elif verifications.filter(status='Pending').exists():
                self.status = 'Pending'
            else:
                self.status = 'Approved'
        self.save()

  
    upload_date = models.DateTimeField(auto_now_add=True)
    expiry_date = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    def clean(self):
        if not self.user and not self.car:
            raise ValidationError('Document must be related to either a user or a car.')
        if self.user and self.car:
            raise ValidationError('Document cannot be related to both a user and a car.')

    def __str__(self):
        if self.user:
            return f"{self.document_type.name} - User: {self.user.get_full_name() or self.user.username}"
        elif self.car:
            return f"{self.document_type.name} - Car ID: {self.car.id}"
        return self.document_type.name
    

    from django.db import models


class DocumentVerification(models.Model):
    VERIFICATION_TYPE_CHOICES = [
        ('Admin', 'Admin'),
        ('ML', 'Machine Learning'),
        ('External', 'External'),
    ]

    STATUS_CHOICES = [
        ('Pending', 'Pending'),
        ('Approved', 'Approved'),
        ('Rejected', 'Rejected'),
    ]

    document = models.ForeignKey('documents.Document', on_delete=models.CASCADE, related_name='verifications')
    verification_type = models.CharField(max_length=20, choices=VERIFICATION_TYPE_CHOICES)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='Pending')
    verified_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        help_text='Only applicable for Admin or External verifications'
    )
    verification_date = models.DateTimeField(auto_now_add=True)
    comments = models.TextField(null=True, blank=True)

    ml_confidence = models.DecimalField(
        max_digits=5, decimal_places=2, null=True, blank=True,
        help_text="Confidence percentage from Machine Learning verification, e.g. 95.50"
    )

    class Meta:
        ordering = ['-verification_date']

    def __str__(self):
        return f"{self.document} - {self.verification_type} - {self.status}"
