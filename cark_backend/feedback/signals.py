from django.db.models.signals import post_save
from django.dispatch import receiver
from django.contrib.contenttypes.models import ContentType
from .models import Rating, Report
from cars.models import Car
from users.models import User, UserRole
from django.db import models

def update_avg_rating_and_reviews(obj, model_class, field_prefix=""):
    content_type = ContentType.objects.get_for_model(model_class)
    ratings = Rating.objects.filter(reviewee_content_type=content_type, reviewee_object_id=obj.id)  # type: ignore
    total_reviews = ratings.count()
    avg_rating = ratings.aggregate(models.Avg('rating'))['rating__avg'] or 0
    setattr(obj, f"{field_prefix}avg_rating", avg_rating)
    setattr(obj, f"{field_prefix}total_reviews", total_reviews)
    obj.save(update_fields=[f"{field_prefix}avg_rating", f"{field_prefix}total_reviews"])

def update_user_aggregate_rating(user):
    userroles = UserRole.objects.filter(user=user)  # type: ignore
    all_ratings = []
    for ur in userroles:
        ct = ContentType.objects.get_for_model(UserRole)
        ratings = Rating.objects.filter(reviewee_content_type=ct, reviewee_object_id=ur.id)  # type: ignore
        all_ratings.extend(list(ratings.values_list('rating', flat=True)))
    total_reviews = len(all_ratings)
    avg_rating = sum(all_ratings) / total_reviews if total_reviews > 0 else 0
    user.avg_rating = avg_rating
    user.total_reviews = total_reviews
    user.save(update_fields=["avg_rating", "total_reviews"])

@receiver(post_save, sender=Rating)
def update_rating_summary(sender, instance, created, **kwargs):
    if not created:
        return
    
    # Get the reviewee object using content type
    reviewee_model = instance.reviewee_content_type.model_class()
    try:
        reviewee = reviewee_model.objects.get(id=instance.reviewee_object_id)  # type: ignore
    except reviewee_model.DoesNotExist:  # type: ignore
        return
    
    if isinstance(reviewee, Car):
        update_avg_rating_and_reviews(reviewee, Car)
    elif isinstance(reviewee, UserRole):
        update_avg_rating_and_reviews(reviewee, UserRole)
        update_user_aggregate_rating(reviewee.user)
    elif hasattr(reviewee, 'avg_rating') and hasattr(reviewee, 'total_reviews'):
        update_avg_rating_and_reviews(reviewee, type(reviewee))

@receiver(post_save, sender=Report)
def update_reports_count(sender, instance, created, **kwargs):
    if not created:
        return
    
    # Get the target object using content type
    target_model = instance.target_content_type.model_class()
    try:
        target = target_model.objects.get(id=instance.target_object_id)  # type: ignore
    except target_model.DoesNotExist:  # type: ignore
        return
    
    if isinstance(target, UserRole):
        user = target.user
        user.reports_count = Report.objects.filter(target_content_type=instance.target_content_type, target_object_id=instance.target_object_id).count()  # type: ignore
        user.save(update_fields=["reports_count"])  # type: ignore 