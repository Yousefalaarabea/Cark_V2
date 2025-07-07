# تحديث حدود الإحداثيات - Coordinates Update Summary

## ملخص التغييرات

تم تحديث حدود الإحداثيات في نظام CARK من 9 أرقام إلى 20 رقم، وزيادة عدد الكسور العشرية من 6 إلى 15 لتحسين دقة تحديد المواقع.

## الملفات المحدثة

### 1. نماذج البيانات (Models)

#### `cark_backend/selfdrive_rentals/models.py`
- `SelfDriveRental` model:
  - `pickup_latitude`: `max_digits=9, decimal_places=6` → `max_digits=20, decimal_places=15`
  - `pickup_longitude`: `max_digits=9, decimal_places=6` → `max_digits=20, decimal_places=15`
  - `dropoff_latitude`: `max_digits=9, decimal_places=6` → `max_digits=20, decimal_places=15`
  - `dropoff_longitude`: `max_digits=9, decimal_places=6` → `max_digits=20, decimal_places=15`

- `SelfDriveLiveLocation` model:
  - `latitude`: `max_digits=9, decimal_places=6` → `max_digits=20, decimal_places=15`
  - `longitude`: `max_digits=9, decimal_places=6` → `max_digits=20, decimal_places=15`

#### `cark_backend/rentals/models.py`
- `PlannedTripStop` model:
  - `latitude`: `max_digits=9, decimal_places=6` → `max_digits=20, decimal_places=15`
  - `longitude`: `max_digits=9, decimal_places=6` → `max_digits=20, decimal_places=15`

### 2. السيريلايزرز (Serializers)

#### `cark_backend/selfdrive_rentals/serializers.py`
- `SelfDriveRentalSerializer`:
  - `pickup_latitude`: `max_digits=9, decimal_places=6` → `max_digits=20, decimal_places=15`
  - `pickup_longitude`: `max_digits=9, decimal_places=6` → `max_digits=20, decimal_places=15`
  - `dropoff_latitude`: `max_digits=9, decimal_places=6` → `max_digits=20, decimal_places=15`
  - `dropoff_longitude`: `max_digits=9, decimal_places=6` → `max_digits=20, decimal_places=15`

### 3. ملفات الهجرة (Migrations)

#### `cark_backend/selfdrive_rentals/migrations/0010_update_coordinates_max_digits.py`
- تم إنشاء ملف هجرة لتحديث max_digits من 9 إلى 20

#### `cark_backend/selfdrive_rentals/migrations/0011_update_coordinates_decimal_places.py`
- تم إنشاء ملف هجرة لتحديث decimal_places من 6 إلى 15

#### `cark_backend/rentals/migrations/0010_update_coordinates_max_digits.py`
- تم إنشاء ملف هجرة لتحديث max_digits من 9 إلى 20

#### `cark_backend/rentals/migrations/0011_update_coordinates_decimal_places.py`
- تم إنشاء ملف هجرة لتحديث decimal_places من 6 إلى 15

## الفوائد من التحديث

1. **دقة أعلى**: السماح بـ 20 رقم بدلاً من 9 يوفر دقة أعلى في تحديد المواقع
2. **كسور عشرية أكثر**: 15 كسر عشري بدلاً من 6 يوفر دقة ميكرومترية
3. **مرونة أكبر**: يمكن الآن تخزين إحداثيات أكثر تفصيلاً
4. **توافق مع أنظمة GPS الحديثة**: يدعم الإحداثيات عالية الدقة

## التطبيق

تم تطبيق التغييرات بنجاح:
- ✅ تم تحديث جميع الملفات المطلوبة
- ✅ تم إنشاء ملفات الهجرة
- ✅ تم تطبيق الهجرة على قاعدة البيانات
- ✅ تم حل مشكلة "Ensure that there are no more than 6 decimal places"

## ملاحظات مهمة

- جميع الإحداثيات الموجودة في قاعدة البيانات ستبقى كما هي
- التحديث يؤثر فقط على الإحداثيات الجديدة التي سيتم إدخالها
- النظام يدعم الآن إحداثيات بدقة أعلى بكثير
- تم حل مشكلة التحقق من عدد الكسور العشرية

## تاريخ التحديث

**التاريخ**: 6 يوليو 2025  
**الوقت**: 19:52  
**الحالة**: مكتمل ✅

### التحديثات:
1. **19:49**: تحديث max_digits من 9 إلى 20
2. **19:52**: تحديث decimal_places من 6 إلى 15 وحل مشكلة التحقق 