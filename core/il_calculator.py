"""
core/il_calculator.py
Pure Uniswap V3 math for concentrated liquidity positions.
Single source of truth for balance calculation, IL, and liquidity derivation.
"""
import math
from typing import Tuple


def compute_v3_balances(
    liquidity: float,
    lower_price: float,
    upper_price: float,
    current_price: float,
) -> Tuple[float, float]:
    """
    Вычисляет реальные количества token0 (x_real) и token1 (y_real)
    в V3 позиции при текущей цене, используя истинную математику Uniswap V3.

    Если P < Pa: позиция 100% в token0, token1 = 0.
    Если P > Pb: позиция 100% в token1, token0 = 0.
    Если Pa <= P <= Pb: оба токена присутствуют.
    """
    if liquidity <= 0 or lower_price <= 0 or upper_price <= lower_price:
        return (0.0, 0.0)

    sqrt_low = math.sqrt(lower_price)
    sqrt_high = math.sqrt(upper_price)

    if current_price < lower_price:
        amount0 = liquidity * (1.0 / sqrt_low - 1.0 / sqrt_high)
        amount1 = 0.0
    elif current_price > upper_price:
        amount0 = 0.0
        amount1 = liquidity * (sqrt_high - sqrt_low)
    else:
        sqrt_cur = math.sqrt(current_price)
        amount0 = liquidity * (1.0 / sqrt_cur - 1.0 / sqrt_high)
        amount1 = liquidity * (sqrt_cur - sqrt_low)

    return (max(0.0, amount0), max(0.0, amount1))


def compute_liquidity_from_deposit(
    lower_price: float,
    upper_price: float,
    initial_price: float,
    amount0_deposited: float,
    amount1_deposited: float,
) -> float:
    """
    Вычисляет L (ликвидность) из начального депозита при цене входа.
    Использует истинную V3 формулу: L = min(L0, L1), где L0 и L1 — это
    ликвидность, выводимая из каждого токена отдельно.

    Если P_entry < Pa: вся позиция в token0.
    Если P_entry > Pb: вся позиция в token1.
    Если Pa <= P_entry <= Pb: L = min(L_from_token0, L_from_token1).
    """
    if lower_price <= 0 or upper_price <= lower_price or initial_price <= 0:
        return 0.0

    sqrt_low = math.sqrt(lower_price)
    sqrt_high = math.sqrt(upper_price)
    sqrt_entry = math.sqrt(initial_price)

    if initial_price < lower_price:
        if amount0_deposited <= 0:
            return 0.0
        return amount0_deposited / ((1.0 / sqrt_low) - (1.0 / sqrt_high))
    elif initial_price > upper_price:
        if amount1_deposited <= 0:
            return 0.0
        return amount1_deposited / (sqrt_high - sqrt_low)
    else:
        denom_x = (1.0 / sqrt_entry - 1.0 / sqrt_high)
        denom_y = (sqrt_entry - sqrt_low)
        L_x = amount0_deposited / denom_x if denom_x > 0 else float('inf')
        L_y = amount1_deposited / denom_y if denom_y > 0 else float('inf')
        if math.isfinite(L_x) or math.isfinite(L_y):
            return min(L_x, L_y)
        return 0.0


def calculate_il(
    current_price: float,
    lower_price: float,
    upper_price: float,
    initial_token0: float,
    initial_token1: float,
    initial_price: float | None = None,
) -> Tuple[float, float, float]:
    """
    Рассчитывает Impermanent Loss и текущую стоимость позиции V3.

    Возвращает (il_percent, il_dollar, current_value).

    ФОРМУЛЫ:
      L = compute_liquidity_from_deposit(...)
      x_real, y_real = compute_v3_balances(L, Pa, Pb, P_current)
      V_current = x_real * P_current + y_real
      V_hold = x_init * P_current + y_init
      IL_usd = V_current - V_hold
      IL_pct = IL_usd / V_hold * 100

    IL отрицателен, когда V_current < V_hold (цена вышла из диапазона).
    """
    if initial_price is None or initial_price <= 0:
        initial_price = current_price

    L = compute_liquidity_from_deposit(
        lower_price, upper_price, initial_price,
        initial_token0, initial_token1
    )

    curr0, curr1 = compute_v3_balances(L, lower_price, upper_price, current_price)

    current_value = curr0 * current_price + curr1
    hold_value = initial_token0 * current_price + initial_token1

    if hold_value > 0:
        il_dollar = current_value - hold_value
        il_percent = il_dollar / hold_value * 100.0
    else:
        il_dollar = 0.0
        il_percent = 0.0

    return (il_percent, il_dollar, current_value)


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