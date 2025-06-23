from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    DocumentTypeViewSet,
    RoleDocumentRequirementViewSet,
    DocumentViewSet,
    DocumentVerificationViewSet,
    MandatoryDocumentsByRoleView,
    DocumentsNeedingVerificationView,
    admin_pending_documents_list,
    documents_by_entity
)


router = DefaultRouter()
router.register('documents/types', DocumentTypeViewSet)
router.register('role-requirements', RoleDocumentRequirementViewSet)
router.register('documents', DocumentViewSet)
router.register('documents/verifications', DocumentVerificationViewSet)

urlpatterns = [
    path('', include(router.urls)),

    path('role/<int:role_id>/mandatory-documents/', MandatoryDocumentsByRoleView.as_view()),
    path('verification/pending/', DocumentsNeedingVerificationView.as_view()),

    path('documents/admin-pending/', admin_pending_documents_list),
     
    # **مسار documents_by_entity**
    path('documents-by-entity/', documents_by_entity),
]
