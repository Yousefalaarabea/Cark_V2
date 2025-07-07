# Current Odometer Reading API Documentation

## إضافة قراءة عداد الكيلومتر الحالي لحجز السيلف درايف

### Endpoint
```
POST /api/selfdrive-rentals/{rental_id}/current-odometer/
```

### الوصف
يسمح هذا الـ API بإضافة قراءة عداد الكيلومتر الحالي لحجز السيلف درايف وحساب جميع التفاصيل والزيادات تلقائياً.

### المتطلبات
- المستخدم يجب أن يكون مسجل دخول
- المستخدم يجب أن يكون إما المستأجر أو صاحب السيارة
- الحجز يجب أن يكون في حالة نشطة (Ongoing أو Confirmed)
- يجب وجود قراءة عداد ابتدائية للحجز

### Request Body
```json
{
    "currentOdometer": 15000.5
}
```

### Parameters
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| currentOdometer | float | Yes | قراءة عداد الكيلومتر الحالية |

### Response

#### Success Response (200 OK)
```json
{
    "rental_id": 123,
    "odometer_details": {
        "start_odometer": 14000.0,
        "current_odometer": 15000.5,
        "used_kilometers": 1000.5,
        "agreed_kilometers": 800.0,
        "extra_kilometers": 200.5
    },
    "time_details": {
        "agreed_end_date": "2024-01-15T18:00:00Z",
        "current_time": "2024-01-16T10:30:00Z",
        "agreed_days": 2,
        "extra_days": 1
    },
    "cost_details": {
        "initial_cost": 500.0,
        "extra_km_rate": 2.0,
        "extra_km_cost": 401.0,
        "daily_price": 200.0,
        "extra_days_cost": 200.0,
        "total_extras_cost": 601.0,
        "final_cost": 1101.0
    },
    "breakdown_summary": {
        "base_cost": 400.0,
        "ctw_fee": 100.0,
        "platform_earnings": 220.2,
        "driver_earnings": 880.8
    },
    "payment_status": {
        "deposit_amount": 75.0,
        "deposit_paid_status": "Paid",
        "remaining_amount": 425.0,
        "remaining_paid_status": "Paid",
        "excess_amount": 601.0,
        "excess_paid_status": "Pending"
    }
}
```

### Response Fields

#### odometer_details
| Field | Type | Description |
|-------|------|-------------|
| start_odometer | float | قراءة العداد الابتدائية |
| current_odometer | float | قراءة العداد الحالية |
| used_kilometers | float | إجمالي الكيلومترات المستخدمة |
| agreed_kilometers | float | الكيلومترات المتفق عليها |
| extra_kilometers | float | الكيلومترات الإضافية |

#### time_details
| Field | Type | Description |
|-------|------|-------------|
| agreed_end_date | string | تاريخ انتهاء الحجز المتفق عليه |
| current_time | string | الوقت الحالي |
| agreed_days | int | عدد الأيام المتفق عليها |
| extra_days | int | عدد الأيام الإضافية |

#### cost_details
| Field | Type | Description |
|-------|------|-------------|
| initial_cost | float | التكلفة الأولية للحجز |
| extra_km_rate | float | سعر الكيلومتر الإضافي |
| extra_km_cost | float | تكلفة الكيلومترات الإضافية |
| daily_price | float | سعر اليوم الواحد |
| extra_days_cost | float | تكلفة الأيام الإضافية |
| total_extras_cost | float | إجمالي تكلفة الزيادات |
| final_cost | float | التكلفة النهائية |

#### breakdown_summary
| Field | Type | Description |
|-------|------|-------------|
| base_cost | float | التكلفة الأساسية |
| ctw_fee | float | رسوم CTW |
| platform_earnings | float | أرباح المنصة |
| driver_earnings | float | أرباح السائق |

#### payment_status
| Field | Type | Description |
|-------|------|-------------|
| deposit_amount | float | مبلغ العربون |
| deposit_paid_status | string | حالة دفع العربون |
| remaining_amount | float | المبلغ المتبقي |
| remaining_paid_status | string | حالة دفع المبلغ المتبقي |
| excess_amount | float | مبلغ الزيادات |
| excess_paid_status | string | حالة دفع الزيادات |

### Error Responses

#### 400 Bad Request
```json
{
    "error": "يجب إدخال قراءة العداد الحالية"
}
```

#### 403 Forbidden
```json
{
    "error": "غير مصرح لك بالوصول لهذا الحجز"
}
```

#### 404 Not Found
```json
{
    "error": "لم يتم العثور على الحجز"
}
```

#### 500 Internal Server Error
```json
{
    "error": "حدث خطأ أثناء معالجة الطلب"
}
```

### أمثلة الاستخدام

#### مثال 1: إضافة قراءة عداد عادية
```bash
curl -X POST \
  http://localhost:8000/api/selfdrive-rentals/123/current-odometer/ \
  -H 'Authorization: Bearer YOUR_TOKEN' \
  -H 'Content-Type: application/json' \
  -d '{
    "currentOdometer": 15000.5
  }'
```

#### مثال 2: إضافة قراءة عداد مع زيادات
```bash
curl -X POST \
  http://localhost:8000/api/selfdrive-rentals/123/current-odometer/ \
  -H 'Authorization: Bearer YOUR_TOKEN' \
  -H 'Content-Type: application/json' \
  -d '{
    "currentOdometer": 16000.0
  }'
```

### ملاحظات مهمة

1. **التحقق من الصلاحيات**: يمكن للمستأجر أو صاحب السيارة فقط إضافة قراءة العداد
2. **حالة الحجز**: يجب أن يكون الحجز في حالة نشطة (Ongoing أو Confirmed)
3. **قراءة العداد الابتدائية**: يجب وجود قراءة عداد ابتدائية للحجز
4. **التحقق من القيم**: القراءة الحالية يجب أن تكون أكبر من أو تساوي القراءة الابتدائية
5. **الحسابات التلقائية**: يتم حساب جميع الزيادات والتكاليف تلقائياً
6. **الإشعارات**: يتم إرسال إشعار للطرف الآخر عند إضافة قراءة العداد
7. **التسجيل**: يتم تسجيل العملية في سجل الحجز

### العمليات التي تتم تلقائياً

1. حساب الكيلومترات المستخدمة
2. حساب الكيلومترات الإضافية
3. حساب الأيام الإضافية
4. حساب التكاليف الإضافية
5. تحديث تفاصيل الحجز
6. تحديث حالة الدفع
7. إرسال إشعار للطرف الآخر
8. تسجيل العملية في السجل 