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


def calculate_required_amounts(
    lower_price: float,
    upper_price: float,
    current_price: float,
    amount0: float | None = None,
    amount1: float | None = None,
) -> Tuple[float, float, float, str]:
    """
    Рассчитывает пропорциональные количества токенов для Uniswap V3 позиции.

    Пользователь вводит amount0 ИЛИ amount1, функция вычисляет необходимое
    количество второго токена для создания сбалансированной позиции.

    Возвращает (amount0_out, amount1_out, L, based_on),
    где based_on указывает, какой токен был исходным ('token0' или 'token1').

    Использует строгую математику Uniswap V3:
      - P < Pa: 100% token0, token1 = 0
      - P > Pb: 100% token1, token0 = 0
      - Pa <= P <= Pb: L = min(L_from_0, L_from_1), пропорции фиксированы
    """
    if lower_price <= 0 or upper_price <= lower_price or current_price <= 0:
        return (0.0, 0.0, 0.0, 'none')

    sqrt_pa = math.sqrt(lower_price)
    sqrt_pb = math.sqrt(upper_price)
    sqrt_p  = math.sqrt(current_price)

    if current_price < lower_price:
        # Price below range — 100% token0, token1 = 0
        denom = (1.0 / sqrt_pa - 1.0 / sqrt_pb)
        if denom <= 0:
            return (0.0, 0.0, 0.0, 'none')
        if amount0 is not None and amount0 > 0:
            L = amount0 / denom
            return (amount0, 0.0, L, 'token0')
        elif amount1 is not None and amount1 > 0:
            L = amount1 / (sqrt_pb - sqrt_pa) if amount1 > 0 else 0.0
            amount0_calc = L * denom
            return (amount0_calc, amount1, L, 'token1')
        else:
            return (0.0, 0.0, 0.0, 'none')

    elif current_price > upper_price:
        # Price above range — 100% token1, token0 = 0
        denom = sqrt_pb - sqrt_pa
        if denom <= 0:
            return (0.0, 0.0, 0.0, 'none')
        if amount1 is not None and amount1 > 0:
            L = amount1 / denom
            return (0.0, amount1, L, 'token1')
        elif amount0 is not None and amount0 > 0:
            L = amount0 / (1.0 / sqrt_pa - 1.0 / sqrt_pb) if amount0 > 0 else 0.0
            amount1_calc = L * denom
            return (amount0, amount1_calc, L, 'token0')
        else:
            return (0.0, 0.0, 0.0, 'none')

    else:
        # Price in range — both tokens present, L = min(L_x, L_y)
        denom_x = (1.0 / sqrt_p - 1.0 / sqrt_pb)
        denom_y = (sqrt_p - sqrt_pa)

        if denom_x <= 0 or denom_y <= 0:
            return (0.0, 0.0, 0.0, 'none')

        if amount0 is not None and amount0 > 0:
            L = amount0 / denom_x
            amount1_calc = L * denom_y
            return (amount0, amount1_calc, L, 'token0')
        elif amount1 is not None and amount1 > 0:
            L = amount1 / denom_y
            amount0_calc = L * denom_x
            return (amount0_calc, amount1, L, 'token1')
        else:
            return (0.0, 0.0, 0.0, 'none')


def calculate_il(
    current_price: float,
    lower_price: float,
    upper_price: float,
    initial_token0: float,
    initial_token1: float,
    initial_price: float | None = None,
    current_token0: float | None = None,
    current_token1: float | None = None,
    investment_goal: str = "preserve_asset",
    entry_usd_total: float | None = None,
) -> Tuple[float, float, float]:
    """
    Рассчитывает Impermanent Loss и текущую стоимость позиции V3.

    Для цели 'accumulate_stable' (накопление стейблов):
      baseline = entry_usd_total (исходный USD-депозит)
      IL считается relative to USD, без капа в 0 (может быть положительным).

    Для всех остальных целей:
      baseline = (initial_token0 * current_price) + initial_token1 (HODL)
      IL capped at 0 (V3 cushion can make V_current > V_hodl).

    Возвращает (il_percent, il_dollar, current_value).
    """
    if initial_price is None or initial_price <= 0:
        initial_price = current_price

    # Calculate current pool value
    if current_token0 is not None and current_token1 is not None:
        current_value = (current_token0 * current_price) + current_token1
    else:
        L = compute_liquidity_from_deposit(
            lower_price, upper_price, initial_price,
            initial_token0, initial_token1
        )
        curr0, curr1 = compute_v3_balances(L, lower_price, upper_price, current_price)
        current_value = (curr0 * current_price) + curr1

    # Goal-based baseline selection
    if investment_goal == 'accumulate_stable':
        # Baseline is the original USD entry value
        if entry_usd_total is not None and entry_usd_total > 0:
            baseline_value = entry_usd_total
        else:
            baseline_value = (initial_token0 * initial_price) + initial_token1
    else:
        # Baseline is token HODL value at current price
        baseline_value = (initial_token0 * current_price) + initial_token1

    # Calculate divergence vs baseline
    if baseline_value > 0:
        il_dollar = current_value - baseline_value
        il_percent = (il_dollar / baseline_value) * 100.0
    else:
        il_dollar = 0.0
        il_percent = 0.0

    # Cap standard IL at 0% (only for non-accumulate_stable goals)
    # Preserve raw il_dollar for UI rendering even when percent is capped
    if investment_goal != 'accumulate_stable':
        if il_percent >= 0:
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