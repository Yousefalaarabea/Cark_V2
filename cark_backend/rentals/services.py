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
# return: قيمة العربون

def calculate_deposit(total_costs):
    return float(total_costs) * 0.15

# حساب عمولة المنصة
# total_costs: التكلفة الإجمالية
# commission_rate: نسبة العمولة (افتراضي 20%)
# return: قيمة العمولة

def calculate_platform_commission(total_costs, commission_rate=0.1):
    return float(total_costs) * float(commission_rate)

# حساب أرباح السائق
# total_costs: التكلفة الإجمالية
# platform_commission: عمولة المنصة
# return: أرباح السائق

def calculate_driver_earnings(total_costs, platform_commission):
    return float(total_costs) - float(platform_commission)

# حساب التكلفة النهائية
# base_cost: تكلفة الإيجار الأساسية
# extra_km_cost: تكلفة الكيلومترات الإضافية
# waiting_time_cost: تكلفة الانتظار
# return: التكلفة النهائية

def calculate_final_cost(base_cost, extra_km_cost, waiting_time_cost):
    return float(base_cost) + float(extra_km_cost) + float(waiting_time_cost)

# حساب إجمالي التكاليف
# base_cost: تكلفة الإيجار الأساسية
# extra_km_cost: تكلفة الكيلومترات الإضافية
# waiting_time_cost: تكلفة الانتظار
# return: الإجمالي

def calculate_total_costs(base_cost, extra_km_cost, waiting_time_cost):
    return float(base_cost) + float(extra_km_cost) + float(waiting_time_cost)

# دالة رئيسية لحساب كل شيء دفعة واحدة
# تعيد dict فيه كل التفاصيل المالية المطلوبة للفلو

def calculate_rental_financials(
    start_date,
    end_date,
    planned_km,
    total_waiting_minutes,
    payment_method,
    daily_price,
    daily_km_limit,
    extra_km_rate,
    extra_hour_cost,
    actual_total_waiting_minutes=None,  # for after trip end
    commission_rate=0.1
):
    duration_days = (end_date - start_date).days + 1
    allowed_km = duration_days * daily_km_limit
    extra_km = max(0, planned_km - allowed_km)
    extra_km_cost = extra_km * extra_km_rate
    waiting_cost = total_waiting_minutes * (extra_hour_cost / 60)

    base_cost = duration_days * daily_price
    total_cost = base_cost + extra_km_cost + waiting_cost

    # Buffer (limits_excess_insurance)
    if payment_method in ['visa', 'wallet']:
        final_cost = total_cost * 1.25
        limits_excess_insurance_amount = total_cost * 0.25
    else:
        final_cost = total_cost
        limits_excess_insurance_amount = 0

    # Deposit and Remaining
    if payment_method in ['visa', 'wallet']:
        deposit = final_cost * 0.15
        remaining = final_cost - deposit
    else:
        deposit = 0
        remaining = final_cost

    # Platform & Driver
    platform_fee = total_cost * commission_rate
    driver_earnings = total_cost * (1 - commission_rate)

    # After trip end (optional refund logic)
    refund = None
    if actual_total_waiting_minutes is not None:
        extra_waiting_minutes = actual_total_waiting_minutes - total_waiting_minutes
        new_excess = extra_waiting_minutes * (extra_hour_cost / 60)
        rental_cost_after_end = total_cost + new_excess
        if extra_waiting_minutes <= 0:
            refund = total_cost * 0.25
        else:
            refund = max(0, total_cost * 0.25 - new_excess)
    
    return {
        'duration_days': duration_days,
        'allowed_km': allowed_km,
        'extra_km': extra_km,
        'extra_km_cost': extra_km_cost,
        'waiting_cost': waiting_cost,
        'base_cost': base_cost,
        'total_cost': total_cost,
        'final_cost': final_cost,
        'limits_excess_insurance_amount': limits_excess_insurance_amount,
        'deposit': deposit,
        'remaining': remaining,
        'platform_fee': platform_fee,
        'driver_earnings': driver_earnings,
        'refund': refund,
    }

# --- دالة دفع وهمية للفيزا ---
def dummy_charge_visa(user, amount):
    print(f"[DUMMY] Charging {amount} from {user.username}'s visa...")
    return True

def dummy_charge_visa_or_wallet(user, amount, method):
    print(f'[DUMMY] Charging {amount} from {user.username} using {method}...')
    return True 
