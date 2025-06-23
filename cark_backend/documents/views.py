from rest_framework import viewsets, generics, status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.decorators import action, api_view
from django.db.models import Q
from documents.models import DocumentVerification
from documents.serializers import DocumentVerificationSerializer
from rest_framework.permissions import IsAuthenticated
from rest_framework.decorators import action
from rest_framework import status
from django.utils import timezone
from rest_framework.generics import ListAPIView

from .models import Document
from .serializers import DocumentSerializer



from .models import (
    DocumentType, RoleDocumentRequirement,
    Document, DocumentVerification
)
from users.models import Role
from .serializers import (
    DocumentTypeSerializer,
    RoleDocumentRequirementSerializer,
    DocumentSerializer,
    DocumentVerificationSerializer
)


# === DocumentType CRUD ===
class DocumentTypeViewSet(viewsets.ModelViewSet):
    queryset = DocumentType.objects.all()
    serializer_class = DocumentTypeSerializer

    def create(self, request, *args, **kwargs):
        # لو البيانات قائمة (list) يعني bulk create
        if isinstance(request.data, list):
            serializer = self.get_serializer(data=request.data, many=True)
            serializer.is_valid(raise_exception=True)
            self.perform_bulk_create(serializer)
            headers = self.get_success_headers(serializer.data)
            return Response(serializer.data, status=status.HTTP_201_CREATED, headers=headers)
        else:
            # إنشاء واحد عادي
            return super().create(request, *args, **kwargs)

    def perform_bulk_create(self, serializer):
        # استخدم bulk_create لتسريع الإدخال
        objs = [DocumentType(**item) for item in serializer.validated_data]
        DocumentType.objects.bulk_create(objs)

# === DocumentType CRUD //////////////////////////////////////////////////////////////////////////////////////////////






# === RoleDocumentRequirement CRUD ===
class RoleDocumentRequirementViewSet(viewsets.ModelViewSet):
    queryset = RoleDocumentRequirement.objects.all()
    serializer_class = RoleDocumentRequirementSerializer

    def create(self, request, *args, **kwargs):
        if isinstance(request.data, list):
            serializer = self.get_serializer(data=request.data, many=True)
            serializer.is_valid(raise_exception=True)
            self.perform_bulk_create(serializer)
            headers = self.get_success_headers(serializer.data)
            return Response(serializer.data, status=status.HTTP_201_CREATED, headers=headers)
        return super().create(request, *args, **kwargs)

    def perform_bulk_create(self, serializer):
        objs = [RoleDocumentRequirement(**item) for item in serializer.validated_data]
        RoleDocumentRequirement.objects.bulk_create(objs)

    
    @action(detail=True, methods=['get'], url_path='documents-for-role')
    def documents_for_role(self, request, pk=None):
        # pk هنا هو role id
        documents = RoleDocumentRequirement.objects.filter(role_id=pk)
        serializer = self.get_serializer(documents, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)
    

################### === Mandatory Documents for Role ===
class MandatoryDocumentsByRoleView(APIView):
    def get(self, request, role_id):
        try:
            role = Role.objects.get(id=role_id)
        except Role.DoesNotExist:
            return Response({'error': 'Role not found'}, status=status.HTTP_404_NOT_FOUND)

        requirements = RoleDocumentRequirement.objects.filter(role=role, is_mandatory=True)
        serializer = RoleDocumentRequirementSerializer(requirements, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)

# === RoleDocumentRequirement CRUD //////////////////////////////////////////////////////////////////////////////////////////////






# === Document CRUD + Custom actions ===
class DocumentViewSet(viewsets.ModelViewSet):
    queryset = Document.objects.all()
    serializer_class = DocumentSerializer
    permission_classes = [IsAuthenticated]

    # check if the user is the owner of the document
    def get_queryset(self):
        user = self.request.user
        if user.is_superuser:
            return Document.objects.all()
        return Document.objects.filter(user=user)

    @action(detail=False, methods=['get'], url_path='my/pending-rejected')
    def my_pending_rejected(self, request):
        user = request.user
        docs = Document.objects.filter(user=user).filter(Q(status='Pending') | Q(status='Rejected'))
        serializer = self.get_serializer(docs, many=True)
        return Response(serializer.data)
    
    @action(detail=False, methods=['get'], url_path='statistics')
    def statistics(self, request):
        total = Document.objects.count()
        pending = Document.objects.filter(status='Pending').count()
        approved = Document.objects.filter(status='Approved').count()
        rejected = Document.objects.filter(status='Rejected').count()

        return Response({
            'total_documents': total,
            'pending': pending,
            'approved': approved,
            'rejected': rejected
        }, status=status.HTTP_200_OK)

# === Document CRUD + Custom actions //////////////////////////////////////////////////////////////////////////////////////////////






# === Document Verification CRUD ===
class DocumentVerificationViewSet(viewsets.ModelViewSet):
    queryset = DocumentVerification.objects.all()
    serializer_class = DocumentVerificationSerializer

# === Document Verification CRUD //////////////////////////////////////////////////////////////////////////////////////////////


# === Documents Needing Verification (Admin or ML) ===

class DocumentVerificationViewSet(viewsets.ModelViewSet):
    queryset = DocumentVerification.objects.all()
    serializer_class = DocumentVerificationSerializer

    @action(detail=False, methods=['patch'], url_path='ml/(?P<doc_id>[^/.]+)')
    def update_ml(self, request, doc_id=None):
        try:
            verification = DocumentVerification.objects.get(document__id=doc_id, verification_type='ML')
        except DocumentVerification.DoesNotExist:
            return Response({'error': 'ML verification not found'}, status=status.HTTP_404_NOT_FOUND)

        verification.status = request.data.get('status', verification.status)
        verification.verified_by = request.user
        verification.verification_date = timezone.now()
        verification.comments = request.data.get('comments', verification.comments)
        verification.ml_confidence = request.data.get('ml_confidence', verification.ml_confidence)
        verification.save()

        serializer = self.get_serializer(verification)
        return Response(serializer.data, status=status.HTTP_200_OK)

    @action(detail=False, methods=['patch'], url_path='admin/(?P<doc_id>[^/.]+)')
    def update_admin(self, request, doc_id=None):
        try:
            verification = DocumentVerification.objects.get(document__id=doc_id, verification_type='Admin')
        except DocumentVerification.DoesNotExist: 
            return Response({'error': 'Admin verification not found'}, status=status.HTTP_404_NOT_FOUND)

        verification.status = request.data.get('status', verification.status)
        verification.verified_by = request.user
        verification.verification_date = timezone.now()
        verification.comments = request.data.get('comments', verification.comments)
        verification.save()

        serializer = self.get_serializer(verification)
        return Response(serializer.data, status=status.HTTP_200_OK)


class DocumentsNeedingVerificationView(ListAPIView):
    queryset = Document.objects.filter(
        Q(verifications__verification_type='Admin', verifications__status='Pending') |
        Q(verifications__verification_type='ML', verifications__status='Pending')
    ).distinct()
    serializer_class = DocumentSerializer




@api_view(['GET'])
def admin_pending_documents_list(request):
    verifications = DocumentVerification.objects.filter(
        verification_type='Admin',
        status='Pending'
    )
    serializer = DocumentVerificationSerializer(verifications, many=True)
    return Response(serializer.data, status=status.HTTP_200_OK)

# === Get documents by user_id or car_id ===
@api_view(['GET'])
def documents_by_entity(request):
    user_id = request.query_params.get('user_id')
    car_id = request.query_params.get('car_id')

    if not user_id and not car_id:
        return Response({'error': 'Please provide either user_id or car_id.'}, status=400)

    if user_id and car_id:
        return Response({'error': 'Please provide only one of user_id or car_id.'}, status=400)

    if user_id:
        documents = Document.objects.filter(user__id=user_id)
    else:
        documents = Document.objects.filter(car__id=car_id)

    serializer = DocumentSerializer(documents, many=True)
    return Response(serializer.data, status=200)
