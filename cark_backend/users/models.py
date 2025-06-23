from django.db import models
from django.contrib.auth.models import AbstractUser, BaseUserManager
from django.db import models  


class UserManager(BaseUserManager):
    def create_user(self, email, phone_number, first_name, last_name, national_id, password=None):
        if not email:
            raise ValueError("The Email field must be set")
        if not password:
            raise ValueError("The Password field must be set")
        if not national_id:
            raise ValueError("The National ID field must be set")

        email = self.normalize_email(email)
        user = self.model(
            email=email,
            phone_number=phone_number,
            first_name=first_name,
            last_name=last_name,
            national_id=national_id
        )
        user.set_password(password)
        user.save(using=self._db)
        return user 

    def create_superuser(self, email, phone_number, first_name, last_name, national_id, password=None):
        user = self.create_user(email, phone_number, first_name, last_name, national_id, password)
        user.is_staff = True
        user.is_superuser = True
        user.save(using=self._db)
        return user 
    
    
class User(AbstractUser):
    username=None
    email = models.EmailField(unique=True)
    phone_number = models.CharField(max_length=20, unique=True)
    email_verified = models.BooleanField(default=False)
    national_id = models.CharField(max_length=14, unique=True, null=True, blank=True, help_text="Egyptian National ID number (14 digits)")
    
    #created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)      

    objects = UserManager()

    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = ['first_name', 'last_name', 'phone_number', 'national_id']

    def __str__(self):
        return self.email
    

class Role(models.Model):
    ROLE_CHOICES = [
        ('Admin', 'Admin'),
        ('Renter', 'Renter'),
        ('Owner', 'Owner'),
        ('Driver', 'Driver'),
    ]
    role_name = models.CharField(max_length=50, choices=ROLE_CHOICES)
    description = models.TextField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.role_name


class UserRole(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    role = models.ForeignKey(Role, on_delete=models.CASCADE)
    assigned_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.user.get_full_name()} - {self.role.role_name}"
