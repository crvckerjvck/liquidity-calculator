import math
import streamlit as st
import json
import os
from data.revert_client import get_pool_address, get_v3_apr_estimate
from core.metrics import calculate_capital_efficiency
from data.price_client import calculate_volatility, get_historical_prices

def load_apr_settings():
    path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'config', 'settings.json')
    try:
        with open(path, 'r', encoding='utf-8') as f:
            settings = json.load(f)
            return {
                "max": settings.get("max_apr_percent", 60.0),
                "min": settings.get("min_apr_percent", 0.5)
            }
    except Exception:
        return {"max": 60.0, "min": 0.5}

def calibrate_with_revert(pool_address: str, lower_tick: int, upper_tick: int) -> float:
    """
    Калибрует внутреннюю модель на основе данных Revert Finance.
    # TODO: Реализовать получение исторической доходности конкретной позиции через Revert.
    """
    return 1.0

@st.cache_data(ttl=3600, show_spinner=False)
def estimate_realistic_apr(
    pair: str, 
    network: str, 
    strategy: str, 
    deposit_usd: float, 
    lower_price: float, 
    upper_price: float,
    current_price: float,
    volatility_annual: float = 50.0, # Добавлен обязательный параметр
    pool_tvl: float = 1000000.0,
    volume_24h: float = 100000.0,
    fee_tier: float = 0.3
) -> float:
    """
    Основной расчёт реалистичного APR.
    Использует данные Revert/Subgraph если доступны, иначе fallback с дисконтами.
    Модель тюнингована под Uniswap V3 (Arbitrum/Mainnet).
    """
    settings = load_apr_settings()
    
    # 0. Валидация входных данных и Fallbacks (Safety Bounds)
    if pool_tvl <= 0 or volume_24h <= 0:
        st.warning(f"⚠️ Данные для {pair} получены с ошибкой (TVL: {pool_tvl}, Vol: {volume_24h}). Используем fallback.")
        pool_tvl = 1000000.0 if pool_tvl <= 0 else pool_tvl
        volume_24h = 100000.0 if volume_24h <= 0 else volume_24h
        
    # TODO: использовать скользящее среднее объёма (EMA) для сглаживания выбросов
    
    # 1. Попытка получить данные через Subgraph (Revert logic)
    fee_bps = int(fee_tier * 10000)
    pool_addr = get_pool_address(pair.split('/')[0], pair.split('/')[1], fee_tier=fee_bps)
    base_apr = None
    if pool_addr:
        base_apr = get_v3_apr_estimate(pool_addr)
        
    # 2. Базовая доходность пула (если нет данных из сабграфа)
    if base_apr is None:
        # Учитываем концентрацию в пулах V3 (TVL floor)
        eff_tvl = max(pool_tvl, volume_24h * 0.5)
        base_apr = (volume_24h * (fee_tier / 100.0) * 365) / eff_tvl * 100.0 if eff_tvl > 0 else 5.0
        
    # 3. Применяем концентрацию (Capital Efficiency)
    width_pct = max(0.05, (upper_price - lower_price) / current_price * 100.0)
    eff_base = calculate_capital_efficiency(current_price, lower_price, upper_price)
    
    # Учёт fee tier в эффективности ( Step 19.3) 
    # При 0.3% фактор = 1.0. При 0.05% фактор ≈ 0.7. При 1% фактор ≈ 1.3.
    fee_factor = (fee_tier / 0.3) ** 0.2
    eff = eff_base * fee_factor
    
    # Смягчаем теоретическую эффективность для V3 (относительный множитель)
    relative_eff = max(1.0, math.sqrt(eff) / 1.5)
    
    apr = base_apr * relative_eff
    
    # 4. ПРИМЕНЕНИЕ ДИСКОНТОВ (Риск-менеджмент)
    # Базовый дисконт от ширины
    discount_width = 0.1 + 0.6 * math.exp(-width_pct / 40.0)
    
    # Коэффициент волатильности ( Step 19.1)
    # При волатильности 70% фактор = 1.0
    vol_factor = min(1.5, max(0.7, volatility_annual / 70.0))
    
    discount = discount_width * vol_factor
    # Ограничения дисконта
    discount = min(0.9, max(0.05, discount))
    
    # Итоговый дисконтированный APR
    apr = apr * (1 - discount)
    
    # 5. Ограничения (Safety Limits)
    apr = max(0.1, min(settings["max"], apr))
    
    return float(apr)
