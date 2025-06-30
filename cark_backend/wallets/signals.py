from django.db.models.signals import post_save
from django.dispatch import receiver
from django.contrib.auth import get_user_model
from .models import Wallet

User = get_user_model()

@receiver(post_save, sender=User)
def create_user_wallet(sender, instance, created, **kwargs):
    """إنشاء محفظة تلقائياً عند إنشاء مستخدم جديد"""
    if created:
        Wallet.objects.get_or_create(user=instance)

@receiver(post_save, sender=User)
def save_user_wallet(sender, instance, **kwargs):
    """حفظ محفظة المستخدم"""
    if hasattr(instance, 'wallet'):
        instance.wallet.save() 