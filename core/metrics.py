import numpy as np
from datetime import date
from data.price_client import calculate_volatility, get_historical_prices

def calculate_actual_apy(initial_body_usd: float, current_body_usd: float, total_fees_usd: float, days_active: int, created_at_str: str = None) -> float | None:
    """
    Рассчитывает фактический APY с учётом изменений тела депозита и комиссий/наград.
    
    Формула:
    - total_gain = (current_body_usd - initial_body_usd) + total_fees_usd
    - actual_apy = (total_gain / initial_body_usd) * (365 / days_active) * 100
    - Ограничение: от -100% до +500%
    
    Parameters:
    - initial_body_usd: начальная стоимость позиции (USD)
    - current_body_usd: текущая стоимость тела депозита (USD), без комиссий
    - total_fees_usd: накопленные комиссии/награды (USD)
    - days_active: количество дней активной позиции (минимум 1)
    
    Returns:
    - float: фактический APY в процентах, или None если данные недостаточны
    """
    if initial_body_usd <= 0 or days_active < 1:
        return None
    
    total_gain = (current_body_usd - initial_body_usd) + total_fees_usd
    actual_apy = (total_gain / initial_body_usd) * (365 / days_active) * 100
    
    # Ограничение от -100% до +500%
    return max(-100, min(500, actual_apy))


def calculate_apr(volume_24h: float, fee_tier: float, tvl_usd: float) -> float:
    """
    Рассчитывает APR на основе объема за 24ч, тира комиссии и TVL.
    APR = (Volume_24h * Fee_Tier * 365) / TVL * 100
    """
    if tvl_usd <= 0:
        return 0.0
    return (volume_24h * fee_tier * 365) / tvl_usd * 100.0

def calculate_capital_efficiency(current_price: float, lower_price: float, upper_price: float) -> float:
    """
    Рассчитывает коэффициент эффективности капитала для V3.
    Чем уже диапазон, тем выше эффективность.
    Формула упрощенная: 1 / (1 - sqrt(lower/upper))
    """
    if lower_price >= upper_price or lower_price <= 0:
        return 1.0
    
    # Эффективность = L_concentrated / L_full_range
    # Для V3: 1 / (1 - (lower/upper)^0.25) -- это одна из версий
    # Используем более стандартную: 1 / (1 - sqrt(lower/price) if price is mid)
    # Для простоты: 1 / (1 - sqrt(lower/upper))
    return 1.0 / (1.0 - (lower_price / upper_price) ** 0.5)

def get_historical_vol_metrics(base_symbol: str, windows: list = [30, 90, 180]) -> dict:
    """
    Получает волатильность и экстремумы (min/max) за разные периоды.
    Возвращает словарь: { 30: {"volatility": 50.0, "min": 1800, "max": 2400}, ... }
    """
    max_days = max(windows)
    prices = get_historical_prices(base_symbol, days=max_days)
    
    if not prices:
        return {w: {"volatility": 0.0, "min": 0.0, "max": 0.0} for w in windows}
        
    # Рассчитываем количество точек на 1 день (эвристика)
    points_per_day = len(prices) / max_days if max_days > 0 else 1
    
    results = {}
    for w in windows:
        # Срез последних w дней (учитываем гранулярность)
        num_points = int(w * points_per_day)
        window_prices = prices[-num_points:] if len(prices) >= num_points else prices
        
        vol = calculate_volatility(window_prices, days_hint=w)
        p_min = min(window_prices) if window_prices else 0.0
        p_max = max(window_prices) if window_prices else 0.0
        
        results[w] = {
            "volatility": vol,
            "min": p_min,
            "max": p_max
        }
        
    return results
