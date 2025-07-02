from datetime import timedelta
from django.utils import timezone
from rest_framework import serializers

from cars.models import Car
from .models import DocumentType, RoleDocumentRequirement, Document, DocumentVerification
from users.models import Role


# ✅ DocumentType
class DocumentTypeSerializer(serializers.ModelSerializer):
    class Meta:
        model = DocumentType
        fields = ['id', 'name', 'description', 'created_at', 'updated_at']


# ✅ RoleDocumentRequirement
class RoleDocumentRequirementSerializer(serializers.ModelSerializer):
    role_name = serializers.CharField(source='role.name', read_only=True)
    document_type_name = serializers.CharField(source='document_type.name', read_only=True)

    class Meta:
        model = RoleDocumentRequirement
        fields = ['id', 'role', 'role_name', 'document_type', 'document_type_name', 'is_mandatory']


# ✅ DocumentVerification
class DocumentVerificationSerializer(serializers.ModelSerializer):
    verified_by_email = serializers.CharField(source='verified_by.email', read_only=True)

    class Meta:
        model = DocumentVerification
        fields = [
            'id', 'document', 'verification_type', 'status', 'verified_by',
            'verified_by_email', 'verification_date', 'comments', 'ml_confidence'
        ]
    def validate(self, data):
        verification_type = data.get('verification_type') or getattr(self.instance, 'verification_type', None)
        verified_by = data.get('verified_by') or getattr(self.instance, 'verified_by', None)
        document = data.get('document') or getattr(self.instance, 'document', None)

        if verification_type == 'ML' and verified_by is not None:
            raise serializers.ValidationError({
                'verified_by': "Must be null for ML verification type."
            })

        if verification_type in ['Admin', 'External'] and verified_by is None:
            raise serializers.ValidationError({
                'verified_by': "Is required for Admin or External verification types."
            })

        if verification_type == 'Admin' and verified_by and not verified_by.is_staff:
            raise serializers.ValidationError({
                'verified_by': "Must be an admin user (is_staff=True) for Admin verification."
            })

        if document and not Document.objects.filter(id=document.id).exists():  # type: ignore
            raise serializers.ValidationError({
                'document': "The related document does not exist."
            })

        return data



# ✅ Document
CAR_DOCUMENT_TYPES = [
    "Car_Photo",
    "Car_License",
    "Vehicle_Violations",
    "Insurance",
    "Car_Test",
]


class DocumentSerializer(serializers.ModelSerializer):
    document_type_name = serializers.CharField(write_only=True)
    document_type = serializers.PrimaryKeyRelatedField(read_only=True)
    user = serializers.PrimaryKeyRelatedField(read_only=True)
    car = serializers.PrimaryKeyRelatedField(queryset=Car.objects.all(), required=False)  # type: ignore
    verifications = DocumentVerificationSerializer(many=True, read_only=True)


    class Meta:
        model = Document
        fields = [
            'id', 'user', 'car', 'file',
            'document_type', 'document_type_name',
            'status', 'upload_date', 'expiry_date', 'updated_at', 'verifications'
        ]
        read_only_fields = ['user', 'status', 'document_type', 'upload_date', 'updated_at', 'verifications', 'expiry_date']

    def validate(self, data):
        car = data.get('car')
        document_type_name = data.get('document_type_name')

        if car and document_type_name not in CAR_DOCUMENT_TYPES:
            raise serializers.ValidationError({
                'document_type_name': f'This document type is not allowed for cars. Allowed: {CAR_DOCUMENT_TYPES}'
            })

        if not car and document_type_name in CAR_DOCUMENT_TYPES:
            raise serializers.ValidationError({
                'document_type_name': f'This document type is restricted to cars only.'
            })

        return data

    def create(self, validated_data):
        request = self.context['request']
        user = request.user
        document_type_name = validated_data.pop('document_type_name', None)

        try:
            document_type = DocumentType.objects.get(name__iexact=document_type_name)  # type: ignore
        except DocumentType.DoesNotExist:  # type: ignore
            raise serializers.ValidationError({'document_type_name': 'Invalid document type name'})
        
        
        car = validated_data.get('car')
        # ✅ التحقق من عدم رفع نفس نوع المستند سابقًا
        if car:
            exists = Document.objects.filter(car=car, document_type=document_type).exists()  # type: ignore
        else:
            exists = Document.objects.filter(user=user, document_type=document_type).exists()  # type: ignore

        if exists:
            raise serializers.ValidationError({'detail': 'This document has already been uploaded.'})
            
        
    # تاريخ الرفع
        upload_date = timezone.now()

    # تعيين تاريخ الانتهاء سنة من تاريخ الرفع
        expiry_date = upload_date + timedelta(days=365)

        # إنشاء المستند إما مع user أو مع car
        document = Document.objects.create(  # type: ignore
            user=user if validated_data.get('car') is None else None,
            car=validated_data.get('car'),
            document_type=document_type,
            status='Pending',
            file=validated_data['file'],
            expiry_date=expiry_date
        )

        # إنشاء الـ verifications تلقائيًا
        DocumentVerification.objects.bulk_create([  # type: ignore
            DocumentVerification(document=document, verification_type='ML', status='Pending'),
            DocumentVerification(document=document, verification_type='Admin', status='Pending'),
        ])

        return document

    def update(self, instance, validated_data):
        instance = super().update(instance, validated_data)
        instance.update_status_from_verifications()
        return instance


    
   

    
