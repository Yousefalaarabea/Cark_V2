# Generated by Django 5.2 on 2025-05-30 15:43

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('users', '0002_remove_user_created_at'),
    ]

    operations = [
        migrations.AddField(
            model_name='user',
            name='national_id',
            field=models.CharField(blank=True, help_text='Egyptian National ID number (14 digits)', max_length=14, null=True, unique=True),
        ),
    ]
