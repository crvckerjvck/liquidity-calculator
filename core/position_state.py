"""
core/position_state.py
Uniswap V3 concentrated liquidity math for current balance computation.
Single source of truth — used by dashboard, recommendations, and rebalance dialogs.
"""
import math
from typing import Tuple


def compute_liquidity(
    initial_price: float,
    lower_price: float,
    upper_price: float,
    amount0: float,
    amount1: float,
) -> float:
    """
    Вычисляет L (ликвидность) по начальному состоянию позиции.
    Используется один раз при создании позиции.
    """
    if initial_price <= 0 or lower_price <= 0 or upper_price <= lower_price:
        return 0.0

    sqrt_p  = math.sqrt(initial_price)
    sqrt_pa = math.sqrt(lower_price)
    sqrt_pb = math.sqrt(upper_price)

    if abs(sqrt_pb - sqrt_pa) < 1e-12:
        return 0.0

    if initial_price <= lower_price:
        # Whole position is in token0
        denom = (1 / sqrt_pa - 1 / sqrt_pb)
        return amount0 / denom if denom > 0 else 0.0
    elif initial_price >= upper_price:
        # Whole position is in token1
        denom = sqrt_pb - sqrt_pa
        return amount1 / denom if denom > 0 else 0.0
    else:
        # Mixed
        denom_x = (1 / sqrt_p - 1 / sqrt_pb)
        denom_y = (sqrt_p - sqrt_pa)
        L_x = amount0 / denom_x if denom_x > 0 else float('inf')
        L_y = amount1 / denom_y if denom_y > 0 else float('inf')
        return min(L_x, L_y) if math.isfinite(L_x) or math.isfinite(L_y) else 0.0


def compute_current_balances(
    liquidity: float,
    lower_price: float,
    upper_price: float,
    current_price: float,
) -> Tuple[float, float]:
    """
    Вычисляет текущее количество token0 и token1 в позиции при current_price.
    Возвращает (amount0, amount1).
    """
    if liquidity <= 0 or lower_price <= 0 or upper_price <= lower_price:
        return (0.0, 0.0)

    sqrt_p  = math.sqrt(max(current_price, 1e-18))
    sqrt_pa = math.sqrt(lower_price)
    sqrt_pb = math.sqrt(upper_price)

    if current_price <= lower_price:
        # Entirely in token0
        amount0 = liquidity * (1 / sqrt_pa - 1 / sqrt_pb)
        return (max(0.0, amount0), 0.0)
    elif current_price >= upper_price:
        # Entirely in token1
        amount1 = liquidity * (sqrt_pb - sqrt_pa)
        return (0.0, max(0.0, amount1))
    else:
        amount0 = liquidity * (1 / sqrt_p - 1 / sqrt_pb)
        amount1 = liquidity * (sqrt_p - sqrt_pa)
        return (max(0.0, amount0), max(0.0, amount1))


def compute_il(
    initial0: float,
    initial1: float,
    current0: float,
    current1: float,
    current_price: float,
) -> Tuple[float, float]:
    """
    Рассчитывает IL относительно HODLing изначальных количеств.
    Возвращает (il_percent, il_dollar).
    Отрицательное значение = убыток vs HODL.
    """
    hold_value = initial0 * current_price + initial1
    pool_value = current0 * current_price + current1

    if hold_value <= 0:
        return (0.0, 0.0)

    il_dollar = pool_value - hold_value
    il_percent = il_dollar / hold_value * 100.0
    return (il_percent, il_dollar)


def range_proximity(current_price: float, lower: float, upper: float) -> dict:
    """
    Возвращает близость цены к границам диапазона.
    proximity_lower: % расстояния от lower (0% = на нижней границе)
    proximity_upper: % расстояния от upper (0% = на верхней границе)
    in_range: True если текущая цена в диапазоне
    """
    if upper <= lower or upper <= 0:
        return {"in_range": False, "proximity_lower": None, "proximity_upper": None, "pct_through": None}

    in_range = lower <= current_price <= upper
    width = upper - lower
    proximity_lower = (current_price - lower) / width * 100.0 if width > 0 else 0
    proximity_upper = (upper - current_price) / width * 100.0 if width > 0 else 0
    pct_through = (current_price - lower) / width * 100.0

    return {
        "in_range": in_range,
        "proximity_lower_pct": round(proximity_lower, 1),
        "proximity_upper_pct": round(proximity_upper, 1),
        "pct_through": round(pct_through, 1),
    }

def get_composition_at_bounds(liquidity: float, lower_price: float, upper_price: float) -> dict:
    """
    Возвращает количество токенов при ценах, равных границам диапазона.
    Использует стандартные формулы Uniswap V3.
    """
    if liquidity <= 0 or lower_price <= 0 or upper_price <= lower_price:
        return {
            "lower": {"token0": 0.0, "token1": 0.0},
            "upper": {"token0": 0.0, "token1": 0.0}
        }

    sqrt_lower = math.sqrt(lower_price)
    sqrt_upper = math.sqrt(upper_price)
    
    # Количество token0 при цене <= lower_price (вся позиция в token0)
    # x = L * (1/sqrt(Pa) - 1/sqrt(Pb))
    token0_at_lower = liquidity * (1.0 / sqrt_lower - 1.0 / sqrt_upper)
    token1_at_lower = 0.0
    
    # Количество token1 при цене >= upper_price (вся позиция в token1)
    # y = L * (sqrt(Pb) - sqrt(Pa))
    token1_at_upper = liquidity * (sqrt_upper - sqrt_lower)
    token0_at_upper = 0.0
    
    return {
        "lower": {"token0": token0_at_lower, "token1": token1_at_lower},
        "upper": {"token0": token0_at_upper, "token1": token1_at_upper}
    }
