# إصلاح مشكلة حفظ الكارت (Save Card)

## المشكلة
لما تدفع بكارت جديد وتدوس "Save Card" من داخل الكارت، الكارت مش بيتسيف في قاعدة البيانات. المشكلة كانت في الـ TOKEN webhook مش بيقدر يلاقي الـ user عشان يحفظ الكارت.

## السبب الجذري
الـ TOKEN webhook كان بيبحث عن الـ user من الـ PaymentTransaction في قاعدة البيانات، لكن الـ PaymentTransaction مش بيتسيف في قاعدة البيانات (معلق). لذلك مش بيقدر يلاقي الـ user ويحفظ الكارت.

## الحلول المطبقة

### 1. تحسين إنشاء الـ merchant_order_id
- تم تحديث `StartPaymentView` ليشمل الـ rental_id والـ rental_type في الـ merchant_order_id
- الـ merchant_order_id الجديد: `{rental_type}_deposit_{rental_id}_{reference}_{user_id}`
- مثال: `selfdrive_deposit_123_uuid_456`

### 2. تحسين الـ TOKEN webhook
- تم إضافة منطق للبحث عن الـ user من الـ merchant_order_id في الـ TOKEN webhook
- يتم استخراج الـ user_id من آخر جزء في الـ merchant_order_id
- تم إضافة fallback للصيغة القديمة: `{reference}_{user_id}`
- تم إضافة logging مفصل للتتبع

### 3. تحسين تتبع البيانات
- يتم البحث عن الـ merchant_order_id في الـ token_obj_data أولاً
- إذا مش موجود، يتم البحث في الـ order data
- يتم طباعة تفاصيل البحث للتتبع

## التحديثات في الكود

### StartPaymentView
```python
# Get rental_id and rental_type from request if available
rental_id = request.data.get("rental_id")
rental_type = request.data.get("rental_type", "rental")

if purpose == "wallet_recharge":
    merchant_order_id_with_user = f"wallet_recharge_{reference}_{user_id}"
elif rental_id:
    # Include rental_id in merchant_order_id for better tracking
    merchant_order_id_with_user = f"{rental_type}_deposit_{rental_id}_{reference}_{user_id}"
else:
    merchant_order_id_with_user = f"{reference}_{user_id}"
```

### TOKEN Webhook
```python
# Try to find user from merchant_order_id in the TOKEN webhook
merchant_order_id = token_obj_data.get("merchant_order_id", "")

# If not in token_obj_data, try to get from order data
if not merchant_order_id and "order" in token_obj_data:
    order_data = token_obj_data.get("order", {})
    merchant_order_id = order_data.get("merchant_order_id", "")

if merchant_order_id:
    parts = merchant_order_id.split('_')
    
    if len(parts) >= 5:  # rental_type_deposit_rental_id_reference_user_id
        user_uuid = parts[-1]  # user_id is the last part
        user_obj = User.objects.get(id=user_uuid)
    elif len(parts) >= 2:  # reference_user_id (fallback format)
        user_uuid = parts[-1]  # user_id is the last part
        user_obj = User.objects.get(id=user_uuid)
```

## كيفية الاختبار

### 1. دفع بكارت جديد مع حفظ الكارت
1. ادفع بكارت جديد
2. ادوس "Save Card" من داخل الكارت
3. تحقق من الـ logs للتأكد من أن الـ TOKEN webhook تم استقباله
4. تحقق من قاعدة البيانات أن الكارت تم حفظه

### 2. تحقق من الـ Logs
ابحث عن هذه الرسائل في الـ logs:
```
🔍 TOKEN webhook - merchant_order_id: selfdrive_deposit_123_uuid_456
🔍 TOKEN webhook - parts: ['selfdrive', 'deposit', '123', 'uuid', '456']
✅ Found user 456 from merchant_order_id for Paymob order 12345
💳 Saved new card (last 4: 1234) for user 456
```

### 3. تحقق من قاعدة البيانات
```sql
SELECT * FROM payments_savedcard WHERE user_id = [user_id] ORDER BY created_at DESC;
```

## الملفات المحدثة
1. `cark_backend/payments/views.py` - تحسين StartPaymentView والـ TOKEN webhook

## ملاحظات مهمة
- الـ merchant_order_id الجديد يحتوي على معلومات أكثر للتتبع
- تم إضافة logging مفصل للتتبع والـ debugging
- الـ fallback mechanism يضمن التوافق مع الصيغة القديمة
- الكارت بيتسيف فقط إذا تم العثور على الـ user بنجاح

## استكشاف الأخطاء
إذا الكارت مش بيتسيف:
1. تحقق من الـ logs للـ TOKEN webhook
2. تأكد من أن الـ merchant_order_id يحتوي على الـ user_id
3. تحقق من أن الـ user موجود في قاعدة البيانات
4. تأكد من أن الـ webhook URL صحيح في Paymob 