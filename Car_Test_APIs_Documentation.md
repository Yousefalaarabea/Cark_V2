# Car Test APIs Documentation

## نظرة عامة
هذه هي APIs للتحقق من صحة بيانات العربيات قبل الحفظ في قاعدة البيانات. تتيح هذه APIs للمطورين والمستخدمين اختبار البيانات والحصول على اقتراحات ومقارنات ذكية.

## الـ APIs الجديدة المحدثة

### 1. تيست البيانات الأساسية (محدث) 🆕
**POST** `/api/cars/test/basic-info/`

تتحقق من البيانات الأساسية للعربية مع فحص ذكي للعربيات المشابهة والمكررة.

#### Request Body:
```json
{
  "model": "Corolla",
  "brand": "Toyota", 
  "car_type": "Sedan",
  "car_category": "Economy",
  "plate_number": "ABC123",
  "year": 2020,
  "color": "أبيض",
  "seating_capacity": 5,
  "transmission_type": "Automatic",
  "fuel_type": "Petrol",
  "current_odometer_reading": 50000
}
```

#### Response (محدث):
```json
{
  "stage": "basic_info",
  "valid": true,
  "errors": {},
  "warnings": [
    "لديك 2 عربية مشابهة بالفعل"
  ],
  "message": "البيانات الأساسية صحيحة!",
  "next_step": "rental_options",
  "existing_car_check": {
    "plate_available": true,
    "existing_car": null,
    "similar_cars": [
      {
        "id": 15,
        "model": "Corolla",
        "brand": "Toyota",
        "year": 2019,
        "plate_number": "XYZ789",
        "status": "Available",
        "match_level": "دقيق"
      }
    ],
    "similar_count": 1
  },
  "market_stats": {
    "total_cars_of_type": 45,
    "popularity": "عالي"
  }
}
```

**التحديثات الجديدة:**
- فحص وجود العربية برقم اللوحة مع تفاصيل المالك
- البحث عن العربيات المشابهة للمستخدم 
- إحصائيات السوق لنوع العربية
- تحذيرات أكثر ذكاءً

---

### 2. تيست خيارات الإيجار (محدث) 🆕
**POST** `/api/cars/test/rental-options/`

تتحقق من خيارات الإيجار مع مقارنة الأسعار بالسوق وتاريخ المستخدم.

#### Request Body:
```json
{
  "available_without_driver": true,
  "available_with_driver": true,
  "daily_rental_price": 350,
  "monthly_rental_price": 8000,
  "daily_rental_price_with_driver": 650,
  "monthly_price_with_driver": 15000
}
```

#### Response (محدث):
```json
{
  "stage": "rental_options",
  "valid": true,
  "errors": {},
  "warnings": [],
  "message": "خيارات الإيجار صحيحة!",
  "next_step": "usage_policy",
  "market_comparison": {
    "market_average": 325.50,
    "your_price": 350,
    "difference_percent": 7.5,
    "status": "مطابق للسوق"
  },
  "user_price_history": [
    {
      "car": "Honda Civic",
      "price": 300,
      "year": 2018
    }
  ],
  "pricing_tips": [
    "السعر المعقول يجذب المزيد من العملاء",
    "راقب أسعار المنافسين في منطقتك",
    "يمكنك تعديل الأسعار لاحقاً حسب الطلب"
  ]
}
```

**التحديثات الجديدة:**
- مقارنة الأسعار مع متوسط السوق
- تاريخ أسعار المستخدم السابقة
- نصائح تسعير ذكية
- تحليل الفروق السعرية

---

### 3. تيست سياسة الاستخدام (محدث) 🆕  
**POST** `/api/cars/test/usage-policy/`

تتحقق من سياسة الاستخدام مع مقارنة بسياسات السوق والمستخدم.

#### Request Body:
```json
{
  "daily_km_limit": 200,
  "extra_km_cost": 2.5,
  "daily_hour_limit": 12,
  "extra_hour_cost": 15
}
```

#### Response (محدث):
```json
{
  "stage": "usage_policy", 
  "valid": true,
  "errors": {},
  "warnings": [],
  "message": "سياسة الاستخدام صحيحة!",
  "next_step": "complete",
  "market_comparison": {
    "market_avg_km_limit": 210.50,
    "market_avg_km_cost": 2.20,
    "your_km_limit": 200,
    "your_km_cost": 2.5,
    "limit_comparison": "أقل من السوق",
    "cost_comparison": "أعلى من السوق"
  },
  "user_policy_history": [
    {
      "car": "Toyota Camry",
      "daily_km_limit": 250,
      "extra_km_cost": 2.0,
      "year": 2019
    }
  ],
  "policy_tips": [
    "حد الكيلومترات المعقول يجذب المستأجرين",
    "تكلفة إضافية معقولة تحمي سيارتك",
    "راقب كيف يستخدم المستأجرون سياساتك"
  ]
}
```

**التحديثات الجديدة:**
- مقارنة مع متوسط سياسات السوق
- تاريخ سياسات المستخدم السابقة
- نصائح سياسة ذكية
- تحليل التوازن بين السعر والحدود

---

### 4. تحقق سريع من رقم اللوحة (محدث) 🆕
**POST** `/api/cars/test/plate-check/`

تحقق سريع وذكي من رقم اللوحة مع اقتراحات.

#### Request Body:
```json
{
  "plate_number": "ABC123"
}
```

#### Response (محدث):
```json
{
  "plate_number": "ABC123",
  "valid_format": true,
  "available": false,
  "status": "موجود بالفعل",
  "existing_car": {
    "id": 25,
    "model": "Corolla", 
    "brand": "Toyota",
    "year": 2020,
    "owner_is_you": false,
    "status": "Available"
  },
  "message": "رقم اللوحة مستخدم من مالك آخر",
  "suggestions": [
    "ABC124",
    "ABC125", 
    "ABC126"
  ],
  "suggestion_message": "اقتراحات متاحة"
}
```

**التحديثات الجديدة:**
- إظهار تفاصيل العربية الموجودة
- تحديد ما إذا كانت العربية للمستخدم نفسه
- اقتراحات أرقام مشابهة متاحة
- رسائل مفيدة حسب حالة العربية

---

### 5. تيست شامل (محدث)
**POST** `/api/cars/test/complete/`

يشغل جميع التحققات مع معاينة التكاليف.

#### Response (محدث):
```json
{
  "stage": "complete",
  "valid": true,
  "errors": {},
  "warnings": [
    "البيانات الأساسية: لديك 2 عربية مشابهة بالفعل",
    "خيارات الإيجار: السعر مطابق للسوق"
  ],
  "summary": {
    "basic_info_valid": true,
    "rental_options_valid": true, 
    "usage_policy_valid": true,
    "ready_to_submit": true
  },
  "cost_preview": {
    "daily_cost_per_km": 1.75,
    "weekly_cost": 2450,
    "monthly_cost": 10500,
    "estimated_monthly_km": 6000
  },
  "message": "جميع بيانات العربية صحيحة وجاهزة للإرسال!",
  "next_action": "submit_car"
}
```

---

### 6. اقتراحات الأسعار الذكية
**POST** `/api/cars/test/pricing-suggestions/`

اقتراحات أسعار ذكية بناءً على نوع العربية والسوق.

#### Response مثال:
```json
{
  "car_info": {
    "type": "SUV",
    "category": "Luxury", 
    "year": 2020,
    "age": 4
  },
  "suggested_prices": {
    "without_driver": {
      "daily": 600,
      "monthly": 15000
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
    "extra_hour_cost": 50
  },
  "price_range": {
    "min": 480,
    "max": 720
  },
  "tips": [
    "اقترح سعر بين 540 - 660 جنيه/يوم",
    "راقب أسعار المنافسين في منطقتك",
    "اضبط الأسعار حسب الطلب والموسم"
  ]
}
```

## المميزات الجديدة

### 🔍 فحص ذكي للعربيات المكررة
- تحقق من وجود العربية برقم اللوحة
- عرض تفاصيل العربية الموجودة
- البحث عن العربيات المشابهة للمستخدم
- تحديد مستوى التطابق (دقيق/مشابه)

### 📊 تحليل السوق والمقارنات
- مقارنة الأسعار مع متوسط السوق
- إحصائيات شعبية نوع العربية
- مقارنة سياسات الاستخدام مع السوق
- عرض تاريخ أسعار وسياسات المستخدم

### 💡 اقتراحات ذكية
- اقتراحات أرقام لوحات متاحة
- نصائح تسعير حسب السوق
- توصيات سياسة الاستخدام
- تحذيرات وإرشادات مخصصة

### 📈 معاينة التكاليف
- حساب تكلفة الكيلو الواحد
- تقدير التكاليف الأسبوعية والشهرية
- توقع الكيلومترات الشهرية
- تحليل العائد المتوقع

## حالات الاستخدام

### للمطورين
```javascript
// تحقق سريع من رقم اللوحة
const plateCheck = await fetch('/api/cars/test/plate-check/', {
  method: 'POST',
  body: JSON.stringify({ plate_number: 'ABC123' })
});

// تحقق من البيانات الأساسية مع فحص التكرار
const basicCheck = await fetch('/api/cars/test/basic-info/', {
  method: 'POST', 
  body: JSON.stringify(carBasicData)
});

// مقارنة الأسعار مع السوق
const pricingCheck = await fetch('/api/cars/test/rental-options/', {
  method: 'POST',
  body: JSON.stringify(pricingData)
});
```

### للمستخدمين
1. **إدخال رقم اللوحة** - يتحقق فورياً من التوفر مع اقتراحات
2. **إدخال بيانات العربية** - يفحص التكرار ويعرض العربيات المشابهة
3. **تحديد الأسعار** - يقارن مع السوق ويعطي نصائح
4. **تحديد سياسة الاستخدام** - يقارن مع المعايير السائدة
5. **المراجعة النهائية** - معاينة شاملة قبل الحفظ

## رموز الحالة والأخطاء

### حالات رقم اللوحة
- `متاح` - رقم اللوحة متاح للاستخدام
- `موجود بالفعل` - رقم مستخدم من مالك آخر  
- `هذه عربيتك بالفعل!` - رقم مستخدم من نفس المستخدم
- `تنسيق خاطئ` - رقم اللوحة غير صحيح

### مقارنات السوق
- `أعلى من السوق` - أكثر من 10% فوق المتوسط
- `أقل من السوق` - أكثر من 10% تحت المتوسط  
- `مطابق للسوق` - ضمن نطاق ±10% من المتوسط

### مستويات التطابق
- `دقيق` - تطابق كامل في الموديل والماركة
- `مشابه` - تطابق في الماركة فقط أو جزئي

## الخلاصة

الـ APIs المحدثة توفر تجربة أذكى وأكثر فائدة للمستخدمين من خلال:

✅ **فحص شامل للتكرار والتطابق**  
✅ **مقارنات ذكية مع السوق**  
✅ **اقتراحات وتوصيات مخصصة**  
✅ **معاينة التكاليف والعوائد**  
✅ **تحذيرات وإرشادات مفيدة**  

هذا يساعد المستخدمين على اتخاذ قرارات أفضل وتجنب الأخطاء الشائعة عند إضافة عربيات جديدة. 