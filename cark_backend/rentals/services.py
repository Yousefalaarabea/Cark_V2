from decimal import Decimal
from datetime import timedelta

# حساب الكيلومترات المسموحة
# rental_days: عدد أيام الإيجار
# daily_km_limit: الحد اليومي للكيلومترات
# return: إجمالي الكيلومترات المسموحة

def calculate_allowed_km(rental_days, daily_km_limit):
    return float(rental_days) * float(daily_km_limit)

# حساب الكيلومترات الإضافية
# planned_km: المسافة المخططة
# allowed_km: الكيلومترات المسموحة
# return: الكيلومترات الإضافية

def calculate_extra_km(planned_km, allowed_km):
    return max(0, float(planned_km) - float(allowed_km))

# حساب تكلفة الكيلومترات الإضافية
# extra_km: الكيلومترات الإضافية
# extra_km_rate: سعر الكيلومتر الإضافي
# return: التكلفة

def calculate_extra_km_cost(extra_km, extra_km_rate):
    return float(extra_km) * float(extra_km_rate)

# حساب تكلفة الانتظار
# total_waiting_minutes: مجموع دقائق الانتظار
# waiting_hour_rate: سعر الساعة
# return: التكلفة

def calculate_waiting_time_cost(total_waiting_minutes, waiting_hour_rate):
    return float(total_waiting_minutes) * (float(waiting_hour_rate) / 60)

# حساب تكلفة الإيجار الأساسية
# rental_days: عدد الأيام
# daily_price: سعر اليوم
# return: التكلفة

def calculate_base_cost(rental_days, daily_price):
    return float(rental_days) * float(daily_price)

# حساب البوفر (25%)
# total_costs: إجمالي التكاليف
# payment_method: طريقة الدفع
# return: قيمة البوفر

def calculate_insurance_buffer(total_costs, payment_method):
    if payment_method in ['wallet', 'visa']:
        return float(total_costs) * 0.25
    return 0.0

# حساب العربون (15%)
# total_costs: إجمالي التكاليف
# insurance_buffer: قيمة البوفر
# return: قيمة العربون

def calculate_deposit(total_costs, insurance_buffer):
    return float(total_costs + insurance_buffer) * 0.15

# حساب عمولة المنصة
# final_cost: التكلفة النهائية
# commission_rate: نسبة العمولة (افتراضي 20%)
# return: قيمة العمولة

def calculate_platform_commission(final_cost, commission_rate=0.2):
    return float(final_cost) * float(commission_rate)

# حساب أرباح السائق
# final_cost: التكلفة النهائية
# platform_commission: عمولة المنصة
# return: أرباح السائق

def calculate_driver_earnings(final_cost, platform_commission):
    return float(final_cost) - float(platform_commission)

# حساب التكلفة النهائية
# base_cost: تكلفة الإيجار الأساسية
# extra_km_cost: تكلفة الكيلومترات الإضافية
# waiting_time_cost: تكلفة الانتظار
# insurance_buffer: البوفر
# return: التكلفة النهائية

def calculate_final_cost(base_cost, extra_km_cost, waiting_time_cost, insurance_buffer):
    return float(base_cost) + float(extra_km_cost) + float(waiting_time_cost) + float(insurance_buffer)

# حساب إجمالي التكاليف بدون البوفر
# base_cost: تكلفة الإيجار الأساسية
# extra_km_cost: تكلفة الكيلومترات الإضافية
# waiting_time_cost: تكلفة الانتظار
# return: الإجمالي

def calculate_total_costs(base_cost, extra_km_cost, waiting_time_cost):
    return float(base_cost) + float(extra_km_cost) + float(waiting_time_cost)

# دالة رئيسية لحساب كل شيء دفعة واحدة
# تعيد dict فيه كل التفاصيل المالية المطلوبة للفلو

def calculate_rental_financials(
    rental_days,
    planned_km,
    daily_km_limit,
    extra_km_rate,
    total_waiting_minutes,
    waiting_hour_rate,
    daily_price,
    payment_method,
    commission_rate=0.2
):
    allowed_km = calculate_allowed_km(rental_days, daily_km_limit)
    extra_km = calculate_extra_km(planned_km, allowed_km)
    extra_km_cost = calculate_extra_km_cost(extra_km, extra_km_rate)
    waiting_time_cost = calculate_waiting_time_cost(total_waiting_minutes, waiting_hour_rate)
    base_cost = calculate_base_cost(rental_days, daily_price)
    total_costs = calculate_total_costs(base_cost, extra_km_cost, waiting_time_cost)
    insurance_buffer = calculate_insurance_buffer(total_costs, payment_method)
    deposit = calculate_deposit(total_costs, insurance_buffer)
    final_cost = calculate_final_cost(base_cost, extra_km_cost, waiting_time_cost, insurance_buffer)
    platform_commission = calculate_platform_commission(final_cost, commission_rate)
    driver_earnings = calculate_driver_earnings(final_cost, platform_commission)
    return {
        'allowed_km': allowed_km,
        'extra_km': extra_km,
        'extra_km_cost': extra_km_cost,
        'waiting_time_cost': waiting_time_cost,
        'base_cost': base_cost,
        'total_costs': total_costs,
        'insurance_buffer': insurance_buffer,
        'deposit': deposit,
        'final_cost': final_cost,
        'platform_commission': platform_commission,
        'driver_earnings': driver_earnings,
    } 