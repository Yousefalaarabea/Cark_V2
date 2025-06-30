# Generated manually to fix balance field defaults

from django.db import migrations, models
from decimal import Decimal


class Migration(migrations.Migration):

    dependencies = [
        ('wallets', '0002_alter_wallettransaction_balance_after_and_more'),
    ]

    operations = [
        migrations.AlterField(
            model_name='wallettransaction',
            name='balance_after',
            field=models.DecimalField(decimal_places=2, default=Decimal('0.00'), max_digits=10),
        ),
        migrations.AlterField(
            model_name='wallettransaction',
            name='balance_before',
            field=models.DecimalField(decimal_places=2, default=Decimal('0.00'), max_digits=10),
        ),
    ] 