"""
core/il_calculator.py
Wrapper for Uniswap V3 math to maintain backward compatibility.
Uses position_state.py logic for accurate L and balance computation.
"""
from core.position_state import compute_liquidity, compute_current_balances, compute_il as calc_il_logic

def calculate_il(current_price: float, lower_price: float, upper_price: float, initial_token0: float, initial_token1: float, initial_price: float | None = None):
    """
    Рассчитывает Impermanent Loss и текущую стоимость позиции.
    """
    # Если начальная цена не задана, используем текущую (упрощение)
    if initial_price is None:
        initial_price = current_price
        
    # 1. Считаем ликвидность L по начальным данным
    L = compute_liquidity(initial_price, lower_price, upper_price, initial_token0, initial_token1)
    
    # 2. Считаем текущие балансы в пуле при новой цене
    curr0, curr1 = compute_current_balances(L, lower_price, upper_price, current_price)
    
    # 3. Считаем IL относительно HODL
    il_percent, il_dollar = calc_il_logic(initial_token0, initial_token1, curr0, curr1, current_price)
    
    current_value = curr0 * current_price + curr1
    
    return il_percent, il_dollar, current_value


def calculate_il_v2(initial_price: float, current_price: float) -> float:
    """
    Возвращает Impermanent Loss в процентах для V2 пула (отрицательное число).
    Формула: IL = 2 * sqrt(price_ratio) / (1 + price_ratio) - 1
    """
    if initial_price <= 0 or current_price <= 0:
        return 0.0
    price_ratio = current_price / initial_price
    il = 2 * (price_ratio ** 0.5) / (1 + price_ratio) - 1
    return il * 100
