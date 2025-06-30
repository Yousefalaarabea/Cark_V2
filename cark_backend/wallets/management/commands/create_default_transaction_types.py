from django.core.management.base import BaseCommand
from wallets.models import TransactionType

class Command(BaseCommand):
    help = 'إنشاء أنواع المعاملات الافتراضية للمحفظة'

    def handle(self, *args, **options):
        default_types = [
            {
                'name': 'شحن محفظة',
                'description': 'إضافة أموال للمحفظة',
                'is_credit': True
            },
            {
                'name': 'سحب من محفظة',
                'description': 'خصم أموال من المحفظة',
                'is_credit': False
            },
            {
                'name': 'تحويل لمستخدم آخر',
                'description': 'تحويل أموال لمستخدم آخر',
                'is_credit': False
            },
            {
                'name': 'تحويل من مستخدم آخر',
                'description': 'استلام أموال من مستخدم آخر',
                'is_credit': True
            },
            {
                'name': 'دفع إيجار',
                'description': 'دفع مبلغ الإيجار',
                'is_credit': False
            },
            {
                'name': 'استرداد إيجار',
                'description': 'استرداد مبلغ الإيجار',
                'is_credit': True
            },
            {
                'name': 'عمولة النظام',
                'description': 'خصم عمولة النظام',
                'is_credit': False
            },
            {
                'name': 'مكافأة',
                'description': 'مكافأة من النظام',
                'is_credit': True
            },
            {
                'name': 'عقوبة',
                'description': 'عقوبة من النظام',
                'is_credit': False
            },
            {
                'name': 'تسوية حساب',
                'description': 'تسوية حساب من الإدارة',
                'is_credit': True
            }
        ]

        created_count = 0
        for type_data in default_types:
            transaction_type, created = TransactionType.objects.get_or_create(
                name=type_data['name'],
                defaults={
                    'description': type_data['description'],
                    'is_credit': type_data['is_credit']
                }
            )
            if created:
                created_count += 1
                self.stdout.write(
                    self.style.SUCCESS(f'تم إنشاء نوع المعاملة: {type_data["name"]}')
                )
            else:
                self.stdout.write(
                    self.style.WARNING(f'نوع المعاملة موجود بالفعل: {type_data["name"]}')
                )

        self.stdout.write(
            self.style.SUCCESS(f'تم إنشاء {created_count} نوع معاملة جديد')
        ) 