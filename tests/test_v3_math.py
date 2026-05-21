"""
Тест корректности V3 математики для концентрированной ликвидности Uniswap V3.
Проверяет расчёт L, x_real, y_real, IL для случая, когда цена вне диапазона снизу.

Входные данные (реальные параметры позиции):
  - Вход: P_entry = 4800
  - Диапазон: Pa = 2691, Pb = 5023
  - Депозит: 0.83 ETH (token0), 26086 USDC (token1)
  - Текущая цена: P = 2118.62 (ниже Pa = 2691)

Ожидаемый результат:
  - Позиция 100% в ETH (USDC = 0)
  - ETH ~7.8-8.2 (НЕ 13.24 как при ошибочном max(L))
  - IL отрицательный
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from core.il_calculator import (
    compute_v3_balances,
    compute_liquidity_from_deposit,
    calculate_il,
)


def test_v3_math_out_of_range_below():
    # Параметры тестовой позиции
    lower = 2691.0
    upper = 5023.0
    entry_price = 4800.0
    x_init = 0.83   # ETH
    y_init = 26086.0  # USDC
    current_price = 2118.62  # Ниже lower!

    # 1. Рассчитываем L
    L = compute_liquidity_from_deposit(lower, upper, entry_price, x_init, y_init)
    print(f"L (ликвидность) = {L:.4f}")
    assert L > 0, "L должна быть > 0"

    # 2. Рассчитываем текущие балансы
    x_real, y_real = compute_v3_balances(L, lower, upper, current_price)
    print(f"\nТекущая цена P = {current_price} (ниже Pa = {lower})")
    print(f"x_real (ETH) = {x_real:.6f}")
    print(f"y_real (USDC) = {y_real:.6f}")

    # 3. Проверяем, что USDC = 0 (позиция 100% в ETH)
    assert y_real == 0.0, f"y_real должен быть 0 при P < Pa, получено {y_real}"

    # 4. Проверяем, что ETH в корректном диапазоне (не 13+)
    print(f"\nОжидаемый ETH: ~7.8-8.2 (min L), НЕ 13.24 (max L)")
    assert 7.0 <= x_real <= 9.0, (
        f"x_real={x_real:.4f} ETH — вне допустимого диапазона 7.0-9.0 ETH. "
        f"Если значение ~13, значит используется max(L) вместо min(L)."
    )

    # 5. Проверяем IL
    il_pct, il_usd, current_value = calculate_il(
        current_price, lower, upper, x_init, y_init, entry_price
    )
    hold_value = x_init * current_price + y_init
    print(f"\nV_current = ${current_value:,.2f}")
    print(f"V_hold    = ${hold_value:,.2f}")
    print(f"IL_usd    = ${il_usd:,.2f}")
    print(f"IL_pct    = {il_pct:.2f}%")

    # IL должен быть отрицательным (цена упала сильно ниже диапазона)
    assert il_pct < 0, f"IL должен быть отрицательным при P < Pa, получено {il_pct:.2f}%"
    assert il_usd < 0, f"IL_usd должен быть отрицательным при P < Pa, получено {il_usd:.2f}"

    # 6. Дополнительная проверка: при P < Pa x_real не должен меняться
    # при ещё более низкой цене
    x_real_at_2000, y_real_at_2000 = compute_v3_balances(L, lower, upper, 2000.0)
    assert abs(x_real_at_2000 - x_real) < 0.001, (
        f"x_real должен быть постоянным при P < Pa: "
        f"{x_real_at_2000:.4f} vs {x_real:.4f}"
    )
    assert y_real_at_2000 == 0.0, "y_real должен быть 0 при любой P < Pa"

    print("\nВсе проверки пройдены! Математика V3 корректна.")


if __name__ == "__main__":
    test_v3_math_out_of_range_below()