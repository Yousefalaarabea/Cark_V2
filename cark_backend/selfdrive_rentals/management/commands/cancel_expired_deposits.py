from django.core.management.base import BaseCommand
from django.utils import timezone
from cark_backend.selfdrive_rentals.models import SelfDriveRental

class Command(BaseCommand):
    help = 'Cancel rentals with expired deposit deadlines'

    def handle(self, *args, **options):
        now = timezone.now()
        expired = SelfDriveRental.objects.filter(
            status='DepositRequired',
            payment__deposit_paid_status__in=['Pending', ''],
            payment__deposit_due_at__lt=now
        )
        count = 0
        for rental in expired:
            rental.status = 'Canceled'
            rental.save()
            count += 1
            self.stdout.write(self.style.WARNING(
                f"Rental #{rental.id} canceled due to expired deposit deadline."
            ))
        self.stdout.write(self.style.SUCCESS(f"Total canceled: {count}")) 