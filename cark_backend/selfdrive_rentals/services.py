def calculate_selfdrive_financials(base_daily_price, num_days):
    """
    - base_daily_price: السعر الأساسي لليوم الأول
    - num_days: عدد أيام الإيجار
    Returns dict: {
        'base_cost_before_discount': ...,
        'discount_percent': ...,
        'base_cost': ...,
        'ctw_fee': ...,
        'final_cost': ...,
    }
    """
    base_cost = float(base_daily_price) * num_days
    discount = max(0, min(num_days - 1, 15) * 0.015)  # بحد أقصى 15 يوم خصم
    base_cost_after_discount = base_cost * (1 - discount)
    ctw_fee = base_cost_after_discount * 0.3
    final_cost = base_cost_after_discount + ctw_fee
    return {
        'base_cost_before_discount': base_cost,
        'discount_percent': discount * 100,
        'base_cost': base_cost_after_discount,
        'ctw_fee': ctw_fee,
        'final_cost': final_cost,
    }
