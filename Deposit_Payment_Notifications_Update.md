# تحديث إشعارات دفع الديبوزيت

## المشكلة
كانت النوتفيكيشن مش بترجع بعد دفع الديبوزيت سواء كان بسيفد كارد أو بينو كارد. المفروض النوتفيكيشن يروح للونر يقول له إن الديبوزيت اتدفع ويقدر يروح لصفحة الـ owner handover.

## الحلول المطبقة

### 1. إضافة النوتفيكيشن للكارت المحفوظ (Saved Card)
- تم إضافة كود النوتفيكيشن في `ChargeSavedCardView` في `payments/views.py`
- النوتفيكيشن بيتم إرساله مباشرة بعد نجاح الدفع بالكارت المحفوظ
- يتم تحديث حالة الدفع في قاعدة البيانات

### 2. تحسين النوتفيكيشن في الـ Webhook
- تم تحديث الـ webhook للتعامل مع الكارت المحفوظ والكارت الجديد
- يتم تحديد نوع الدفع (new_card أو saved_card) تلقائياً
- يتم إرسال النوتفيكيشن للونر والرينتر

### 3. تحسين تتبع الـ Payment Objects
- تم إضافة منطق للبحث عن الـ payment object بالـ rental_id من الـ merchant_order_id
- تم تحسين إنشاء الـ merchant_order_id ليشمل الـ rental_id والـ rental_type

## البيانات المرسلة في النوتفيكيشن

### للونر (Owner)
```json
{
  "rentalId": "رقم الرحلة",
  "renterId": "رقم الرينتر",
  "carId": "رقم السيارة",
  "status": "حالة الرحلة",
  "startDate": "تاريخ البداية",
  "endDate": "تاريخ النهاية",
  "pickupAddress": "عنوان الاستلام",
  "dropoffAddress": "عنوان التسليم",
  "renterName": "اسم الرينتر",
  "carName": "اسم السيارة",
  "depositAmount": "مبلغ الديبوزيت",
  "transactionId": "رقم المعاملة",
  "paymentMethod": "طريقة الدفع (new_card أو saved_card)",
  "cardLast4": "آخر 4 أرقام الكارت",
  "cardBrand": "نوع الكارت",
  "remainingAmount": "المبلغ المتبقي",
  "totalAmount": "إجمالي المبلغ",
  "rentalPaymentMethod": "طريقة دفع الرحلة",
  "cashCollectionRequired": "هل يحتاج جمع نقدي",
  "cashAmountToCollect": "المبلغ النقدي المطلوب جمعه",
  "automaticPayment": "هل الدفع تلقائي",
  "selectedCardInfo": "معلومات الكارت المختار",
  "plannedKm": "الكيلومترات المخططة",
  "dailyPrice": "السعر اليومي",
  "totalDays": "عدد الأيام",
  "rentalType": "نوع الرحلة",
  "ownerEarnings": "أرباح المالك",
  "platformFee": "رسوم المنصة",
  "commissionRate": "نسبة العمولة",
  "handoverInstructions": "تعليمات التسليم",
  "nextAction": "الخطوة التالية",
  "handoverType": "نوع التسليم",
  "handoverMessage": "رسالة التسليم",
  "handoverStatus": "حالة التسليم",
  "handoverActions": "إجراءات التسليم",
  "handoverNotes": "ملاحظات التسليم",
  "handoverWarnings": "تحذيرات التسليم",
  "handoverChecklist": "قائمة مراجعة التسليم",
  "handoverSummary": "ملخص التسليم"
}
```

### للرينتر (Renter)
```json
{
  "rentalId": "رقم الرحلة",
  "carId": "رقم السيارة",
  "status": "حالة الرحلة",
  "startDate": "تاريخ البداية",
  "endDate": "تاريخ النهاية",
  "pickupAddress": "عنوان الاستلام",
  "dropoffAddress": "عنوان التسليم",
  "carName": "اسم السيارة",
  "ownerName": "اسم المالك",
  "depositAmount": "مبلغ الديبوزيت",
  "transactionId": "رقم المعاملة",
  "paymentMethod": "طريقة الدفع",
  "cardLast4": "آخر 4 أرقام الكارت",
  "cardBrand": "نوع الكارت"
}
```

## Navigation IDs
- `DEP_OWNER`: للونر - يذهب لصفحة owner handover
- `REN_ONT_TRP`: للرينتر - يذهب لصفحة on the way

## الملفات المحدثة
1. `cark_backend/payments/views.py` - إضافة النوتفيكيشن للكارت المحفوظ وتحسين الـ webhook

## كيفية الاختبار
1. دفع ديبوزيت بكارت جديد - يجب أن يظهر النوتفيكيشن للونر
2. دفع ديبوزيت بكارت محفوظ - يجب أن يظهر النوتفيكيشن للونر
3. النوتفيكيشن يجب أن يحتوي على كل البيانات المطلوبة لصفحة owner handover
4. عند الضغط على النوتفيكيشن يجب أن يذهب للصفحة الصحيحة

## ملاحظات مهمة
- النوتفيكيشن بيتم إرساله للونر والرينتر
- البيانات تشمل كل المعلومات المطلوبة لصفحة owner handover
- يتم تحديث حالة الرحلة إلى "Confirmed" بعد نجاح الدفع
- يتم حفظ رقم المعاملة في قاعدة البيانات للرجوع إليه لاحقاً 