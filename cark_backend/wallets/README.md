# نظام المحفظة الداخلية (Wallet System)

## نظرة عامة

نظام المحفظة الداخلية هو نظام متكامل لإدارة الأموال داخل التطبيق، يتيح للمستخدمين:
- شحن محافظهم بأموال
- سحب أموال من محافظهم
- التحويل بين المستخدمين
- تتبع جميع المعاملات المالية
- دفع الإيجارات والخدمات من المحفظة

## المكونات الرئيسية

### 1. النماذج (Models)

#### Wallet
- المحفظة الرئيسية لكل مستخدم
- يحتوي على الرصيد الحالي وحالة المحفظة
- مرتبط بمستخدم واحد فقط (OneToOne)

#### TransactionType
- أنواع المعاملات المالية
- يحدد ما إذا كانت المعاملة إضافة أو خصم
- أمثلة: شحن محفظة، دفع إيجار، تحويل، إلخ

#### WalletTransaction
- سجل جميع المعاملات المالية
- يحتوي على تفاصيل كل معاملة (المبلغ، الرصيد قبل وبعد، الحالة)
- مرتبط بنوع المعاملة والمحفظة

#### WalletRecharge
- طلبات شحن المحفظة
- يدعم طرق دفع متعددة (بطاقة، تحويل بنكي، نقدي)
- مرتبط بمعاملات الدفع الخارجية

#### WalletWithdrawal
- طلبات سحب من المحفظة
- يدعم طرق سحب متعددة (تحويل بنكي، نقدي)
- يتطلب موافقة الإدارة

### 2. الخدمات (Services)

#### WalletService
- إدارة المحافظ الأساسية
- إضافة وخصم الأموال
- التحويل بين المحافظ

#### WalletRechargeService
- إدارة طلبات الشحن
- معالجة مدفوعات الشحن

#### WalletWithdrawalService
- إدارة طلبات السحب
- معالجة طلبات السحب من قبل الإدارة

#### WalletTransactionService
- إدارة معاملات المحفظة
- تتبع تاريخ المعاملات
- إحصائيات المعاملات

### 3. API Endpoints

#### للمستخدمين العاديين
- `GET /api/wallets/balance/` - عرض رصيد المحفظة
- `GET /api/wallets/transactions/` - تاريخ المعاملات
- `GET /api/wallets/transactions/summary/` - ملخص المعاملات
- `POST /api/wallets/recharge/` - شحن المحفظة
- `POST /api/wallets/withdraw/` - طلب سحب
- `POST /api/wallets/transfer/` - تحويل لمستخدم آخر

#### للإدارة
- `GET /api/wallets/admin/wallets/` - قائمة جميع المحافظ
- `GET /api/wallets/admin/wallets/{id}/` - تفاصيل محفظة معينة
- `GET /api/wallets/admin/withdrawals/` - قائمة طلبات السحب
- `POST /api/wallets/admin/withdrawals/{id}/process/` - معالجة طلب سحب
- `POST /api/wallets/admin/withdrawals/{id}/cancel/` - إلغاء طلب سحب

#### Webhooks
- `POST /api/wallets/webhook/payment/` - webhook لمعالجة مدفوعات الشحن

## كيفية الاستخدام

### 1. إنشاء أنواع المعاملات الافتراضية

```bash
python manage.py create_default_transaction_types
```

### 2. شحن المحفظة

```python
from wallets.services import WalletService

# شحن مباشر
transaction = WalletService.add_funds_to_wallet(
    user=user,
    amount=Decimal('100.00'),
    transaction_type_name='شحن محفظة',
    description='شحن عبر البطاقة'
)

# شحن عبر API
POST /api/wallets/recharge/
{
    "amount": "100.00",
    "method": "card",
    "description": "شحن المحفظة"
}
```

### 3. دفع من المحفظة

```python
# دفع إيجار
transaction = WalletService.deduct_funds_from_wallet(
    user=user,
    amount=Decimal('50.00'),
    transaction_type_name='دفع إيجار',
    description='دفع إيجار السيارة',
    reference_id=str(rental.id),
    reference_type='rental'
)
```

### 4. التحويل بين المستخدمين

```python
# تحويل أموال
result = WalletService.transfer_between_wallets(
    sender=sender_user,
    recipient_email='recipient@example.com',
    amount=Decimal('30.00'),
    description='تحويل تجريبي'
)

# عبر API
POST /api/wallets/transfer/
{
    "recipient_email": "recipient@example.com",
    "amount": "30.00",
    "description": "تحويل تجريبي"
}
```

### 5. طلب سحب

```python
# إنشاء طلب سحب
withdrawal = WalletWithdrawalService.create_withdrawal_request(
    user=user,
    amount=Decimal('100.00'),
    method='bank_transfer',
    bank_account='1234567890',
    bank_name='بنك مصر',
    description='سحب للبنك'
)

# عبر API
POST /api/wallets/withdraw/
{
    "amount": "100.00",
    "method": "bank_transfer",
    "bank_account": "1234567890",
    "bank_name": "بنك مصر",
    "description": "سحب للبنك"
}
```

## التكامل مع النظام

### 1. دفع الإيجارات

```python
# في نظام الإيجار
from wallets.services import WalletService

def pay_rental_with_wallet(rental, user):
    try:
        transaction = WalletService.deduct_funds_from_wallet(
            user=user,
            amount=rental.total_amount,
            transaction_type_name='دفع إيجار',
            description=f'دفع إيجار السيارة {rental.car.plate_number}',
            reference_id=str(rental.id),
            reference_type='rental'
        )
        rental.payment_status = 'paid'
        rental.wallet_transaction = transaction
        rental.save()
        return True
    except ValueError as e:
        # الرصيد غير كافي
        return False
```

### 2. استرداد الأموال

```python
# استرداد مبلغ الإيجار
def refund_rental_payment(rental):
    if rental.wallet_transaction:
        WalletService.add_funds_to_wallet(
            user=rental.user,
            amount=rental.total_amount,
            transaction_type_name='استرداد إيجار',
            description=f'استرداد إيجار السيارة {rental.car.plate_number}',
            reference_id=str(rental.id),
            reference_type='rental_refund'
        )
```

### 3. عمولات النظام

```python
# خصم عمولة النظام
def deduct_system_commission(rental, commission_amount):
    WalletService.deduct_funds_from_wallet(
        user=rental.car.owner,
        amount=commission_amount,
        transaction_type_name='عمولة النظام',
        description=f'عمولة إيجار السيارة {rental.car.plate_number}',
        reference_id=str(rental.id),
        reference_type='commission'
    )
```

## الأمان والتحقق

### 1. التحقق من الرصيد
- يتم التحقق من كفاية الرصيد قبل أي خصم
- استخدام transactions atomic لضمان سلامة البيانات

### 2. تتبع المعاملات
- كل معاملة لها معرف فريد (UUID)
- حفظ الرصيد قبل وبعد كل معاملة
- ربط المعاملات بالمراجع الخارجية

### 3. صلاحيات الإدارة
- طلبات السحب تتطلب موافقة الإدارة
- الإدارة يمكنها معالجة أو إلغاء طلبات السحب
- تتبع جميع العمليات الإدارية

## الاختبارات

```bash
# تشغيل اختبارات المحفظة
python manage.py test wallets

# تشغيل اختبارات محددة
python manage.py test wallets.tests.WalletServiceTest
```

## الإدارة

### 1. لوحة الإدارة
- عرض جميع المحافظ
- إدارة طلبات السحب
- تتبع المعاملات
- إحصائيات النظام

### 2. الأوامر الإدارية
```bash
# إنشاء أنواع المعاملات الافتراضية
python manage.py create_default_transaction_types
```

## ملاحظات مهمة

1. **الأمان**: جميع المعاملات تتم داخل transactions atomic
2. **التتبع**: كل معاملة لها سجل كامل مع المراجع
3. **المرونة**: النظام يدعم أنواع معاملات متعددة
4. **التكامل**: يمكن ربطه بسهولة مع أنظمة الدفع الخارجية
5. **الإدارة**: واجهة إدارية شاملة لإدارة النظام

## التطوير المستقبلي

1. **الإشعارات**: إرسال إشعارات للمعاملات المهمة
2. **التقارير**: تقارير مفصلة عن المعاملات
3. **الحدود**: تحديد حدود للتحويلات والسحوبات
4. **التحقق**: إضافة مستويات تحقق إضافية
5. **التكامل**: دعم طرق دفع إضافية 