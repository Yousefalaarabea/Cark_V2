# Car Validation Test APIs Documentation

هذه الـ APIs مخصصة لتيست وتحقق من بيانات العربية أثناء مراحل الإضافة بدون حفظ في قاعدة البيانات. الهدف منها التأكد من صحة البيانات قبل الإرسال النهائي.

## 1. Car Validation Test API

**Endpoint:** `POST /api/cars/test-validation/`

**Description:** تيست شامل لبيانات العربية في مراحل مختلفة

### Request Body:
```json
{
  "stage": "basic_info|rental_options|usage_policy|complete",
  // بيانات العربية حسب المرحلة
}
```

### Stages:

#### A. Basic Info Stage (`stage: "basic_info"`)
```json
{
  "stage": "basic_info",
  "model": "Camry",
  "brand": "Toyota", 
  "car_type": "Sedan",
  "car_category": "Economy",
  "plate_number": "ABC123",
  "year": 2020,
  "color": "White",
  "seating_capacity": 5,
  "transmission_type": "Automatic",
  "fuel_type": "Petrol",
  "current_odometer_reading": 50000
}
```

**Response:**
```json
{
  "stage": "basic_info",
  "valid": true,
  "errors": {},
  "warnings": ["High odometer reading may affect rental attractiveness"],
  "message": "Basic info validation complete"
}
```

#### B. Rental Options Stage (`stage: "rental_options"`)
```json
{
  "stage": "rental_options",
  "available_without_driver": true,
  "available_with_driver": true,
  "daily_rental_price": 300,
  "monthly_rental_price": 7500,
  "yearly_rental_price": 82500,
  "daily_rental_price_with_driver": 570,
  "monthly_price_with_driver": 14250
}
```

**Response:**
```json
{
  "stage": "rental_options",
  "valid": true,
  "errors": {},
  "warnings": [],
  "message": "Rental options validation complete"
}
```

#### C. Usage Policy Stage (`stage: "usage_policy"`)
```json
{
  "stage": "usage_policy",
  "daily_km_limit": 250,
  "extra_km_cost": 1.5,
  "daily_hour_limit": 12,
  "extra_hour_cost": 25
}
```

**Response:**
```json
{
  "stage": "usage_policy",
  "valid": true,
  "errors": {},
  "warnings": [],
  "message": "Usage policy validation complete"
}
```

#### D. Complete Validation (`stage: "complete"`)
يجمع جميع البيانات ويعمل تحقق شامل:

```json
{
  "stage": "complete",
  // جميع البيانات من المراحل السابقة
  "model": "Camry",
  "brand": "Toyota",
  // ... باقي البيانات
}
```

**Response:**
```json
{
  "stage": "complete",
  "valid": true,
  "errors": {},
  "warnings": [],
  "summary": {
    "basic_info": true,
    "rental_options": true,
    "usage_policy": true,
    "ready_to_submit": true
  },
  "message": "Car data is ready for submission!"
}
```

### Error Response Example:
```json
{
  "stage": "basic_info",
  "valid": false,
  "errors": {
    "plate_number": "Plate number already exists",
    "year": "Year must be between 1990 and 2025",
    "daily_rental_price": "Price must be greater than 0"
  },
  "warnings": ["Daily price seems low, consider market rates"],
  "message": "Please fix the errors above"
}
```

---

## 2. Plate Number Check API

**Endpoint:** `POST /api/cars/check-plate/`

**Description:** تحقق من توفر رقم اللوحة وصحة التنسيق

### Request Body:
```json
{
  "plate_number": "ABC123"
}
```

### Response:
```json
{
  "plate_number": "ABC123",
  "valid_format": true,
  "available": true,
  "message": "Plate number is available"
}
```

### Error Response:
```json
{
  "plate_number": "XYZ999",
  "valid_format": true,
  "available": false,
  "message": "Plate number already exists"
}
```

---

## 3. Pricing Suggestion API

**Endpoint:** `POST /api/cars/suggest-pricing/`

**Description:** اقتراح أسعار بناءً على نوع العربية والسوق

### Request Body:
```json
{
  "car_type": "SUV",
  "car_category": "Luxury", 
  "year": 2020
}
```

### Response:
```json
{
  "car_info": {
    "type": "SUV",
    "category": "Luxury",
    "year": 2020,
    "age": 4
  },
  "suggested_pricing": {
    "without_driver": {
      "daily": 600,
      "monthly": 15000,
      "yearly": 165000
    },
    "with_driver": {
      "daily": 1140,
      "monthly": 28500
    }
  },
  "suggested_policy": {
    "daily_km_limit": 200,
    "extra_km_cost": 4.5,
    "daily_hour_limit": 12,
    "extra_hour_cost": 50.0
  },
  "market_analysis": {
    "price_range": {
      "min": 480,
      "max": 720
    },
    "competitiveness": "Premium"
  },
  "recommendations": [
    "Consider pricing between 540 - 660 EGP/day",
    "Monitor competitor prices in your area",
    "Adjust pricing based on demand and seasonality"
  ]
}
```

---

## Validation Rules

### Basic Info Validations:
- **Required Fields:** model, brand, car_type, car_category, plate_number, year, color, seating_capacity, transmission_type, fuel_type, current_odometer_reading
- **Plate Number:** يجب أن يكون بالتنسيق المصري (عربي أو إنجليزي + أرقام) وغير مكرر
- **Year:** بين 1990 و 2025
- **Seating Capacity:** بين 2 و 15 مقعد
- **Odometer:** لا يمكن أن يكون سالب
- **Choices:** يجب أن تكون من الخيارات المحددة مسبقاً

### Rental Options Validations:
- **Availability:** يجب تفعيل خيار واحد على الأقل (مع أو بدون سائق)
- **Pricing:** الأسعار يجب أن تكون أكبر من صفر
- **Driver Premium:** السعر مع سائق يجب أن يكون أعلى من بدون سائق
- **Monthly Pricing:** يجب أن يكون منطقي مقارنة بالسعر اليومي

### Usage Policy Validations:
- **KM Limit:** يجب أن يكون أكبر من صفر
- **Extra KM Cost:** يجب أن يكون أكبر من صفر
- **Hour Limit:** اختياري، لكن إذا تم تحديده يجب أن يكون بين 1-24 ساعة
- **Extra Hour Cost:** مطلوب إذا تم تحديد حد الساعات

### Warnings (تحذيرات لا تمنع الإرسال):
- سيارات أقدم من 2010 قد تقل عليها الطلبات
- أسعار منخفضة جداً أو مرتفعة جداً
- حدود كيلومترات منخفضة أو مرتفعة جداً
- عداد مسافات عالي قد يؤثر على الجاذبية

---

## Usage Examples

### Frontend Integration Example:

```javascript
// تحقق من المرحلة الأولى
const validateBasicInfo = async (carData) => {
  const response = await fetch('/api/cars/test-validation/', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'Authorization': `Bearer ${token}`
    },
    body: JSON.stringify({
      stage: 'basic_info',
      ...carData
    })
  });
  
  const result = await response.json();
  
  if (result.valid) {
    // البيانات صحيحة، يمكن الانتقال للمرحلة التالية
    console.log('Basic info is valid');
    if (result.warnings.length > 0) {
      // عرض التحذيرات للمستخدم
      showWarnings(result.warnings);
    }
  } else {
    // عرض الأخطاء للمستخدم
    showErrors(result.errors);
  }
};

// تحقق من رقم اللوحة أثناء الكتابة
const checkPlateNumber = async (plateNumber) => {
  const response = await fetch('/api/cars/check-plate/', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'Authorization': `Bearer ${token}`
    },
    body: JSON.stringify({ plate_number: plateNumber })
  });
  
  const result = await response.json();
  
  if (!result.available) {
    showError('Plate number already exists');
  } else if (!result.valid_format) {
    showError('Invalid plate number format');
  } else {
    showSuccess('Plate number is available');
  }
};

// اقتراح الأسعار
const getSuggestedPricing = async (carType, carCategory, year) => {
  const response = await fetch('/api/cars/suggest-pricing/', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'Authorization': `Bearer ${token}`
    },
    body: JSON.stringify({
      car_type: carType,
      car_category: carCategory,
      year: year
    })
  });
  
  const result = await response.json();
  
  // عرض الأسعار المقترحة للمستخدم
  fillSuggestedPrices(result.suggested_pricing);
  showRecommendations(result.recommendations);
};
```

---

## Benefits

1. **تحسين تجربة المستخدم:** التحقق الفوري من البيانات بدون انتظار الإرسال النهائي
2. **تقليل الأخطاء:** اكتشاف المشاكل مبكراً قبل محاولة الحفظ
3. **توجيه المستخدم:** اقتراحات وتحذيرات لتحسين البيانات
4. **سرعة الاستجابة:** APIs سريعة لأنها لا تحفظ في قاعدة البيانات
5. **مرونة:** يمكن التحقق من مرحلة محددة أو جميع المراحل

---

## Error Codes

- `400` - بيانات مطلوبة ناقصة أو تنسيق خاطئ
- `401` - غير مصرح (مطلوب تسجيل دخول)
- `200` - نجح التحقق (حتى لو كانت هناك أخطاء في البيانات، الـ response سيكون 200 مع تفاصيل الأخطاء) 