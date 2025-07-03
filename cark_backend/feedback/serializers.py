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
                rental = Rental.objects.get(id=rental_id)  # type: ignore
            except Rental.DoesNotExist:  # type: ignore
                raise serializers.ValidationError({'rental_id': 'Rental does not exist.'})
        elif rental_type == 'selfdriverental':
            try:
                rental = SelfDriveRental.objects.get(id=rental_id)  # type: ignore
            except SelfDriveRental.DoesNotExist:  # type: ignore
                raise serializers.ValidationError({'rental_id': 'SelfDriveRental does not exist.'})
        else:
            raise serializers.ValidationError({'rental_type': 'Invalid rental type.'})

        # تحقق من وجود الكيان المستهدف
        if reviewee_type == 'userrole':
            try:
                userrole = UserRole.objects.get(id=reviewee_id)  # type: ignore
            except UserRole.DoesNotExist:  # type: ignore
                raise serializers.ValidationError({'reviewee_id': 'UserRole does not exist.'})
            # تحقق أن الـ UserRole مرتبط فعلاً بالرحلة
            if rental_type == 'rental':
                # في rentals، المالك هو مالك السيارة
                if not (userrole.user == rental.car.owner or userrole.user == rental.renter):
                    raise serializers.ValidationError({'reviewee_id': 'UserRole is not related to this rental.'})
            elif rental_type == 'selfdriverental':
                # في SelfDriveRental، المالك هو مالك السيارة
                if not (userrole.user == rental.car.owner or userrole.user == rental.renter):
                    raise serializers.ValidationError({'reviewee_id': 'UserRole is not related to this selfdrive rental.'})
            # منع التقييم الذاتي
            if userrole.user == user:
                raise serializers.ValidationError({'reviewee_id': 'You cannot rate yourself.'})
        elif reviewee_type == 'car':
            try:
                car = Car.objects.get(id=reviewee_id)  # type: ignore
            except Car.DoesNotExist:  # type: ignore
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
        reviewee_content_type = ContentType.objects.get(model=reviewee_type)
        rental_content_type = ContentType.objects.get(model=rental_type)
        if Rating.objects.filter(reviewer=user, reviewee_content_type=reviewee_content_type, reviewee_object_id=reviewee_id, rental_content_type=rental_content_type, rental_object_id=rental_id).exists():  # type: ignore
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
        return Rating.objects.create(  # type: ignore
            reviewer=reviewer,
            reviewee_content_type=reviewee_content_type,
            reviewee_object_id=reviewee_id,
            rental_content_type=rental_content_type,
            rental_object_id=rental_id,
            **validated_data
        )


# Serializers منفصلة لكل نوع تقييم
class BaseRatingSerializer(serializers.ModelSerializer):
    rental_type = serializers.CharField(write_only=True)
    rental_id = serializers.IntegerField(write_only=True)

    class Meta:
        model = Rating
        fields = ['id', 'reviewer', 'rental_type', 'rental_id', 'rating', 'notes', 'created_at']
        read_only_fields = ['id', 'reviewer', 'created_at']

    def validate_rating(self, value):
        if not (1 <= value <= 5):
            raise serializers.ValidationError("Rating must be between 1 and 5.")
        return value

    def validate_rental_data(self, rental_type, rental_id):
        """التحقق من صحة بيانات الرحلة"""
        if rental_type == 'rental':
            try:
                return Rental.objects.get(id=rental_id)  # type: ignore
            except Rental.DoesNotExist:  # type: ignore
                raise serializers.ValidationError({'rental_id': 'Rental does not exist.'})
        elif rental_type == 'selfdriverental':
            try:
                return SelfDriveRental.objects.get(id=rental_id)  # type: ignore
            except SelfDriveRental.DoesNotExist:  # type: ignore
                raise serializers.ValidationError({'rental_id': 'SelfDriveRental does not exist.'})
        else:
            raise serializers.ValidationError({'rental_type': 'Invalid rental type.'})

    def get_rental_content_type(self, rental_type):
        """الحصول على ContentType الصحيح للرحلة"""
        if rental_type == 'rental':
            return ContentType.objects.get_for_model(Rental)
        elif rental_type == 'selfdriverental':
            return ContentType.objects.get_for_model(SelfDriveRental)
        else:
            raise serializers.ValidationError({'rental_type': 'Invalid rental type.'})

    def check_duplicate_rating(self, user, reviewee_content_type, reviewee_object_id, rental_type, rental_id):
        """التحقق من التقييمات المكررة"""
        rental_content_type = self.get_rental_content_type(rental_type)
        
        if Rating.objects.filter(  # type: ignore
            reviewer=user, 
            reviewee_content_type=reviewee_content_type, 
            reviewee_object_id=reviewee_object_id, 
            rental_content_type=rental_content_type, 
            rental_object_id=rental_id
        ).exists():
            raise serializers.ValidationError({'error': 'You have already rated this entity for this rental.'})


class RateOwnerSerializer(BaseRatingSerializer):
    """Serializer لتقييم المالك من قبل المستأجر"""
    
    def validate(self, attrs):
        rental_type = attrs.get('rental_type')
        rental_id = attrs.get('rental_id')
        user = self.context['request'].user

        # التحقق من الرحلة
        rental = self.validate_rental_data(rental_type, rental_id)

        # التحقق أن المستخدم هو المستأجر
        if user != rental.renter:
            raise serializers.ValidationError({'error': 'Only renters can rate owners.'})

        # التحقق أن الرحلة انتهت
        if rental.status != 'Finished':
            raise serializers.ValidationError({'error': 'Cannot rate before rental is finished.'})

        # التحقق من وجود UserRole للمالك
        owner_userrole = UserRole.objects.filter(user=rental.car.owner, role__role_name='Owner').first()  # type: ignore
        if not owner_userrole:
            raise serializers.ValidationError({'error': 'Owner UserRole not found.'})

        # التحقق من التقييمات المكررة
        self.check_duplicate_rating(
            user, 
            ContentType.objects.get_for_model(UserRole), 
            owner_userrole.id, 
            rental_type, 
            rental_id
        )

        attrs['_owner_userrole'] = owner_userrole
        return attrs

    def create(self, validated_data):
        rental_type = validated_data.pop('rental_type')
        rental_id = validated_data.pop('rental_id')
        owner_userrole = validated_data.pop('_owner_userrole')
        
        return Rating.objects.create(  # type: ignore
            reviewer=self.context['request'].user,
            reviewee_content_type=ContentType.objects.get_for_model(UserRole),
            reviewee_object_id=owner_userrole.id,
            rental_content_type=self.get_rental_content_type(rental_type),
            rental_object_id=rental_id,
            **validated_data
        )


class RateRenterSerializer(BaseRatingSerializer):
    """Serializer لتقييم المستأجر من قبل المالك"""
    
    def validate(self, attrs):
        rental_type = attrs.get('rental_type')
        rental_id = attrs.get('rental_id')
        user = self.context['request'].user

        # التحقق من الرحلة
        rental = self.validate_rental_data(rental_type, rental_id)

        # التحقق أن المستخدم هو المالك
        if user != rental.car.owner:
            raise serializers.ValidationError({'error': 'Only owners can rate renters.'})

        # التحقق أن الرحلة انتهت
        if rental.status != 'Finished':
            raise serializers.ValidationError({'error': 'Cannot rate before rental is finished.'})

        # التحقق من وجود UserRole للمستأجر
        renter_userrole = UserRole.objects.filter(user=rental.renter, role__role_name='Renter').first()  # type: ignore
        if not renter_userrole:
            raise serializers.ValidationError({'error': 'Renter UserRole not found.'})

        # التحقق من التقييمات المكررة
        self.check_duplicate_rating(
            user, 
            ContentType.objects.get_for_model(UserRole), 
            renter_userrole.id, 
            rental_type, 
            rental_id
        )

        attrs['_renter_userrole'] = renter_userrole
        return attrs

    def create(self, validated_data):
        rental_type = validated_data.pop('rental_type')
        rental_id = validated_data.pop('rental_id')
        renter_userrole = validated_data.pop('_renter_userrole')
        
        return Rating.objects.create(  # type: ignore
            reviewer=self.context['request'].user,
            reviewee_content_type=ContentType.objects.get_for_model(UserRole),
            reviewee_object_id=renter_userrole.id,
            rental_content_type=self.get_rental_content_type(rental_type),
            rental_object_id=rental_id,
            **validated_data
        )


class RateCarSerializer(BaseRatingSerializer):
    """Serializer لتقييم السيارة من قبل المستأجر"""
    
    def validate(self, attrs):
        rental_type = attrs.get('rental_type')
        rental_id = attrs.get('rental_id')
        user = self.context['request'].user

        # التحقق من الرحلة
        rental = self.validate_rental_data(rental_type, rental_id)

        # التحقق أن المستخدم هو المستأجر
        if user != rental.renter:
            raise serializers.ValidationError({'error': 'Only renters can rate cars.'})

        # التحقق أن الرحلة انتهت
        if rental.status != 'Finished':
            raise serializers.ValidationError({'error': 'Cannot rate before rental is finished.'})

        # التحقق من التقييمات المكررة
        self.check_duplicate_rating(
            user, 
            ContentType.objects.get_for_model(Car), 
            rental.car.id, 
            rental_type, 
            rental_id
        )

        attrs['_rental'] = rental
        return attrs

    def create(self, validated_data):
        rental_type = validated_data.pop('rental_type')
        rental_id = validated_data.pop('rental_id')
        rental = validated_data.pop('_rental')
        
        return Rating.objects.create(  # type: ignore
            reviewer=self.context['request'].user,
            reviewee_content_type=ContentType.objects.get_for_model(Car),
            reviewee_object_id=rental.car.id,
            rental_content_type=self.get_rental_content_type(rental_type),
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
                userrole = UserRole.objects.get(id=target_id)  # type: ignore
            except UserRole.DoesNotExist:  # type: ignore
                raise serializers.ValidationError({'target_id': 'UserRole does not exist.'})
            # منع التبليغ الذاتي
            if userrole.user == reporter:
                raise serializers.ValidationError({'target_id': 'You cannot report yourself.'})
        elif target_type == 'car':
            try:
                car = Car.objects.get(id=target_id)  # type: ignore
            except Car.DoesNotExist:  # type: ignore
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
        return Report.objects.create(  # type: ignore
            reporter=reporter,
            target_content_type=target_content_type,
            target_object_id=target_id,
            **validated_data
        ) 
