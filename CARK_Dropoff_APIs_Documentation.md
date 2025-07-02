# CARK SelfDrive Drop-off & Handover APIs

## Overview
هذه مجموعة من الـ APIs الجديدة لإدارة عملية تسليم السيارات في نهاية الإيجار، حساب الزيادات، وعرض الملخصات النهائية.

## Authentication
جميع الـ APIs تتطلب JWT token في الـ header:
```
Authorization: Bearer your_jwt_token_here
```

---

## 1. Calculate Excess Fees
**حساب الزيادات بدون حفظ في قاعدة البيانات**

### Endpoint
```
POST /api/selfdrive-rentals/{rental_id}/calculate-excess/
```

### Parameters
- `rental_id` (URL): معرف الإيجار
- `end_odometer_value` (required): قراءة العداد النهائية
- `actual_dropoff_time` (optional): وقت التسليم الفعلي بصيغة ISO 8601

### Request Body
```json
{
  "end_odometer_value": 15000,
  "actual_dropoff_time": "2025-01-20T20:00:00Z"
}
```

### Response Example
```json
{
  "rental_id": 1,
  "calculation_time": "2025-01-20T20:00:00Z",
  "km_details": {
    "start_odometer": 12000,
    "end_odometer": 15000,
    "actual_km": 3000,
    "allowed_km": 2500,
    "extra_km": 500,
    "extra_km_cost": 2.5,
    "extra_km_fee": 1250
  },
  "time_details": {
    "planned_end_time": "2025-01-20T18:00:00Z",
    "actual_dropoff_time": "2025-01-20T20:00:00Z",
    "late_days": 1,
    "late_fee_per_day": 650,
    "late_fee": 650
  },
  "cost_summary": {
    "initial_cost": 5000,
    "extra_km_fee": 1250,
    "late_fee": 650,
    "total_excess": 1900,
    "final_cost": 6900
  },
  "earnings": {
    "commission_rate": 0.15,
    "platform_earnings": 1035,
    "driver_earnings": 5865
  },
  "payment_info": {
    "payment_method": "visa",
    "will_auto_charge": true,
    "requires_cash_collection": false
  }
}
```

### Use Cases
- عرض الزيادات للمستأجر قبل التأكيد النهائي
- حساب المبلغ المطلوب تحصيله نقداً للمالك
- التحقق من التكلفة النهائية قبل الدفع

---

## 2. Renter Dropoff Preview
**معاينة تفاصيل التسليم للمستأجر**

### Endpoint
```
GET /api/selfdrive-rentals/{rental_id}/renter-dropoff-preview/
```

### Access
- المستأجر فقط
- حالة الإيجار: Ongoing

### Response Example
```json
{
  "rental_info": {
    "id": 1,
    "car": "Toyota Camry",
    "owner_name": "أحمد محمد",
    "planned_end_time": "2025-01-20T18:00:00Z",
    "current_time": "2025-01-20T20:00:00Z"
  },
  "odometer_info": {
    "start_value": 12000,
    "allowed_km": 2500,
    "extra_km_cost": 2.5
  },
  "payment_info": {
    "method": "visa",
    "initial_cost": 5000,
    "existing_excess": 0,
    "auto_charge_excess": true
  },
  "required_steps": [
    "Upload current car image",
    "Upload odometer image and enter current value",
    "Add any notes about car condition",
    "Confirm handover"
  ],
  "warnings": {
    "late_return": true,
    "auto_charge": true
  }
}
```

### Use Cases
- عرض الخطوات المطلوبة للمستأجر
- تحذير من التأخير والرسوم الإضافية
- إعلام المستأجر بطريقة الدفع والخصم التلقائي

---

## 3. Owner Dropoff Preview
**معاينة تفاصيل التسليم للمالك**

### Endpoint
```
GET /api/selfdrive-rentals/{rental_id}/owner-dropoff-preview/
```

### Access
- المالك فقط
- متطلب: يجب أن يكون المستأجر قد أكمل التسليم

### Response Example
```json
{
  "rental_info": {
    "id": 1,
    "car": "Toyota Camry",
    "renter_name": "سارة أحمد",
    "renter_return_time": "2025-01-20T20:15:00Z"
  },
  "excess_summary": {
    "total_amount": 1900,
    "details": [
      {
        "type": "extra_km",
        "description": "زيادة كيلومترات: 500 كم",
        "calculation": "500 × 2.5 = 1250 جنيه",
        "amount": 1250
      },
      {
        "type": "late_fee",
        "description": "رسوم تأخير: 1 يوم",
        "calculation": "1 × 650 = 650 جنيه",
        "amount": 650
      }
    ],
    "payment_method": "cash",
    "already_charged": false
  },
  "cash_collection": {
    "required": true,
    "amount_to_collect": 1900,
    "status": "pending"
  },
  "earnings_summary": {
    "final_cost": 6900,
    "platform_commission": 1035,
    "owner_earnings": 5865
  },
  "required_steps": [
    "Review excess charges",
    "Collect cash payment",
    "Add any notes about car condition",
    "Confirm handover completion"
  ],
  "uploaded_images": {
    "car_images": 2,
    "odometer_images": 1
  }
}
```

### Use Cases
- عرض المبلغ المطلوب تحصيله نقداً
- تفصيل الزيادات والرسوم
- عرض أرباح المالك النهائية
- التأكد من اكتمال رفع الصور

---

## 4. Rental Summary
**الملخص الشامل للإيجار**

### Endpoint
```
GET /api/selfdrive-rentals/{rental_id}/summary/
```

### Access
- المستأجر والمالك

### Response Example
```json
{
  "rental_info": {
    "id": 1,
    "status": "Finished",
    "car": "Toyota Camry",
    "renter": "سارة أحمد",
    "owner": "أحمد محمد",
    "planned_period": {
      "start": "2025-01-15T10:00:00Z",
      "end": "2025-01-20T18:00:00Z",
      "duration_days": 6
    }
  },
  "actual_usage": {
    "actual_dropoff_time": "2025-01-20T20:15:00Z",
    "odometer": {
      "start": 12000,
      "end": 15000,
      "total_km": 3000
    }
  },
  "cost_breakdown": {
    "initial_cost": 5000,
    "base_cost": 4500,
    "ctw_fee": 500,
    "extra_charges": {
      "extra_km_fee": 1250,
      "late_fee": 650,
      "total_extras": 1900
    },
    "final_cost": 6900
  },
  "payment_details": {
    "method": "cash",
    "deposit": {
      "amount": 1000,
      "status": "Paid",
      "paid_at": "2025-01-14T15:30:00Z"
    },
    "remaining": {
      "amount": 4000,
      "status": "Paid",
      "paid_at": "2025-01-15T10:00:00Z"
    },
    "excess": {
      "amount": 1900,
      "status": "Paid",
      "paid_at": "2025-01-20T20:30:00Z"
    }
  },
  "earnings": {
    "commission_rate": 0.15,
    "platform_earnings": 1035,
    "owner_earnings": 5865
  },
  "timeline": {
    "created_at": "2025-01-14T14:00:00Z",
    "pickup_completed": "2025-01-15T10:15:00Z",
    "return_completed": "2025-01-20T20:30:00Z"
  },
  "user_role": "renter"
}
```

### Use Cases
- عرض تقرير نهائي شامل بعد انتهاء الإيجار
- أرشفة تفاصيل الإيجار
- مراجعة الدفعات والأرباح

---

## Error Responses

### 404 - Rental Not Found
```json
{
  "error": "Rental not found"
}
```

### 403 - Permission Denied
```json
{
  "error": "Only renter can access this"
}
```

### 400 - Invalid Status
```json
{
  "error": "Rental is not ongoing"
}
```

### 400 - Missing Required Data
```json
{
  "error": "end_odometer_value is required"
}
```

### 400 - Renter Must Complete First
```json
{
  "error": "Renter must complete dropoff first"
}
```

---

## Test Scenarios

### Scenario 1: Normal Return (No Excess)
```bash
# Calculate excess with no extra charges
POST /api/selfdrive-rentals/1/calculate-excess/
{
  "end_odometer_value": 14000,
  "actual_dropoff_time": "2025-01-20T17:00:00Z"
}

# Expected: total_excess = 0, no extra fees
```

### Scenario 2: Late Return with Extra KM (Visa Payment)
```bash
# Calculate excess with both late fee and extra km
POST /api/selfdrive-rentals/1/calculate-excess/
{
  "end_odometer_value": 15500,
  "actual_dropoff_time": "2025-01-20T22:00:00Z"
}

# Expected: auto_charge = true, requires_cash_collection = false
```

### Scenario 3: Cash Payment with Excess
```bash
# Owner preview for cash collection
GET /api/selfdrive-rentals/1/owner-dropoff-preview/

# Expected: cash_collection.required = true, amount_to_collect > 0
```

### Scenario 4: Completed Rental Summary
```bash
# Get comprehensive summary
GET /api/selfdrive-rentals/1/summary/

# Expected: Complete breakdown with all payments and timeline
```

---

## Integration Flow

### For Renter Drop-off:
1. `GET renter-dropoff-preview/` - عرض الخطوات المطلوبة
2. `POST calculate-excess/` - حساب الزيادات قبل التأكيد
3. Upload images and confirm handover (existing APIs)

### For Owner Drop-off:
1. `GET owner-dropoff-preview/` - عرض المبلغ المطلوب تحصيله
2. Collect cash if required
3. Confirm handover completion (existing APIs)

### For Final Summary:
1. `GET summary/` - عرض الملخص الشامل بعد الانتهاء

---

## Notes
- جميع المبالغ بالجنيه المصري
- التواريخ بصيغة ISO 8601 مع UTC timezone
- رسوم التأخير = 30% زيادة على السعر اليومي لكل يوم تأخير
- العمولة الافتراضية = 15% من التكلفة النهائية
- الدفع التلقائي يتم للفيزا والمحفظة فقط
- الدفع النقدي يتطلب تحصيل من المالك 