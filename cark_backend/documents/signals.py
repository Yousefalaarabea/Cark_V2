from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from .models import DocumentVerification

@receiver(post_save, sender=DocumentVerification)
@receiver(post_delete, sender=DocumentVerification)
def update_document_status(sender, instance, **kwargs):
    document = instance.document
    document.update_status_from_verifications()
