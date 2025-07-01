from rest_framework import serializers
from .models import Rating, Report
from django.contrib.contenttypes.models import ContentType
from users.models import UserRole
from rentals.models import Rental
from selfdrive_rentals.models import SelfDriveRental
from cars.models import Car

class RatingSerializer(serializers.ModelSerializer):
    reviewee_type = serializers.CharField(write_only=True)
    reviewee_id = serializers.IntegerField(write_only=True)
    rental_type = serializers.CharField(write_only=True)
    rental_id = serializers.IntegerField(write_only=True)

    class Meta:
        model = Rating
        fields = ['id', 'reviewer', 'reviewee_type', 'reviewee_id', 'rental_type', 'rental_id', 'rating', 'notes', 'created_at']
        read_only_fields = ['id', 'reviewer', 'created_at']

    def validate_rating(self, value):
        if not (1 <= value <= 5):
            raise serializers.ValidationError("Rating must be between 1 and 5.")
        return value

    def validate(self, attrs):
        reviewee_type = attrs.get('reviewee_type')
        reviewee_id = attrs.get('reviewee_id')
        rental_type = attrs.get('rental_type')
        rental_id = attrs.get('rental_id')
        user = self.context['request'].user

        # تحقق من وجود الرحلة
        if rental_type == 'rental':
            try:
                rental = Rental.objects.get(id=rental_id)
            except Rental.DoesNotExist:
                raise serializers.ValidationError({'rental_id': 'Rental does not exist.'})
        elif rental_type == 'selfdriverental':
            try:
                rental = SelfDriveRental.objects.get(id=rental_id)
            except SelfDriveRental.DoesNotExist:
                raise serializers.ValidationError({'rental_id': 'SelfDriveRental does not exist.'})
        else:
            raise serializers.ValidationError({'rental_type': 'Invalid rental type.'})

        # تحقق من وجود الكيان المستهدف
        if reviewee_type == 'userrole':
            try:
                userrole = UserRole.objects.get(id=reviewee_id)
            except UserRole.DoesNotExist:
                raise serializers.ValidationError({'reviewee_id': 'UserRole does not exist.'})
            # تحقق أن الـ UserRole مرتبط فعلاً بالرحلة
            if rental_type == 'rental':
                # في rentals غالبًا فيه حقل renter/owner
                if not (userrole.user == rental.owner or userrole.user == rental.renter):
                    raise serializers.ValidationError({'reviewee_id': 'UserRole is not related to this rental.'})
            elif rental_type == 'selfdriverental':
                if not (userrole.user == rental.owner or userrole.user == rental.renter):
                    raise serializers.ValidationError({'reviewee_id': 'UserRole is not related to this selfdrive rental.'})
            # منع التقييم الذاتي
            if userrole.user == user:
                raise serializers.ValidationError({'reviewee_id': 'You cannot rate yourself.'})
        elif reviewee_type == 'car':
            try:
                car = Car.objects.get(id=reviewee_id)
            except Car.DoesNotExist:
                raise serializers.ValidationError({'reviewee_id': 'Car does not exist.'})
            # تحقق أن السيارة هي فعلاً سيارة الرحلة
            if rental_type == 'rental':
                if rental.car_id != car.id:
                    raise serializers.ValidationError({'reviewee_id': 'This car is not related to the rental.'})
            elif rental_type == 'selfdriverental':
                if rental.car_id != car.id:
                    raise serializers.ValidationError({'reviewee_id': 'This car is not related to the selfdrive rental.'})
        else:
            raise serializers.ValidationError({'reviewee_type': 'Invalid reviewee type.'})

        # منع التقييم المكرر
        from django.contrib.contenttypes.models import ContentType
        reviewee_content_type = ContentType.objects.get(model=reviewee_type)
        rental_content_type = ContentType.objects.get(model=rental_type)
        if Rating.objects.filter(reviewer=user, reviewee_content_type=reviewee_content_type, reviewee_object_id=reviewee_id, rental_content_type=rental_content_type, rental_object_id=rental_id).exists():
            raise serializers.ValidationError('You have already rated this entity for this rental.')

        return attrs

    def create(self, validated_data):
        reviewer = self.context['request'].user
        reviewee_type = validated_data.pop('reviewee_type')
        reviewee_id = validated_data.pop('reviewee_id')
        rental_type = validated_data.pop('rental_type')
        rental_id = validated_data.pop('rental_id')
        reviewee_content_type = ContentType.objects.get(model=reviewee_type)
        rental_content_type = ContentType.objects.get(model=rental_type)
        return Rating.objects.create(
            reviewer=reviewer,
            reviewee_content_type=reviewee_content_type,
            reviewee_object_id=reviewee_id,
            rental_content_type=rental_content_type,
            rental_object_id=rental_id,
            **validated_data
        )

class ReportSerializer(serializers.ModelSerializer):
    target_type = serializers.CharField(write_only=True)
    target_id = serializers.IntegerField(write_only=True)

    class Meta:
        model = Report
        fields = ['id', 'reporter', 'target_type', 'target_id', 'reason', 'details', 'status', 'created_at']
        read_only_fields = ['id', 'reporter', 'status', 'created_at']

    def validate(self, attrs):
        target_type = attrs.get('target_type')
        target_id = attrs.get('target_id')
        reporter = self.context['request'].user

        if target_type == 'user':
            try:
                userrole = UserRole.objects.get(id=target_id)
            except UserRole.DoesNotExist:
                raise serializers.ValidationError({'target_id': 'UserRole does not exist.'})
            # منع التبليغ الذاتي
            if userrole.user == reporter:
                raise serializers.ValidationError({'target_id': 'You cannot report yourself.'})
        elif target_type == 'car':
            try:
                car = Car.objects.get(id=target_id)
            except Car.DoesNotExist:
                raise serializers.ValidationError({'target_id': 'Car does not exist.'})
        else:
            raise serializers.ValidationError({'target_type': 'Invalid target type.'})
        return attrs

    def create(self, validated_data):
        reporter = self.context['request'].user
        target_type = validated_data.pop('target_type')
        target_id = validated_data.pop('target_id')
        from django.contrib.contenttypes.models import ContentType
        target_content_type = ContentType.objects.get(model=target_type)
        return Report.objects.create(
            reporter=reporter,
            target_content_type=target_content_type,
            target_object_id=target_id,
            **validated_data
        ) 