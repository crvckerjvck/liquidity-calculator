from typing import Dict, List, Optional
import streamlit as st
from data.db import get_all_positions # Corrected path
# from core.metrics import calculate_volatility # already imported in de-facto use cases

# Доступные тиры для Uniswap V3
FEE_TIERS = {
    0.01: {"name": "0.01%", "tick_spacing": 1, "description": "Для стейблкоинов и очень низкой волатильности"},
    0.05: {"name": "0.05%", "tick_spacing": 10, "description": "Для стабильных пар, много объёма"},
    0.30: {"name": "0.3%", "tick_spacing": 60, "description": "Основной тир для ETH, BTC, основных пар"},
    1.00: {"name": "1%", "tick_spacing": 200, "description": "Для волатильных и экзотических пар"},
}

def classify_pair_type(pair: str) -> str:
    """Определяет тип пары по символам."""
    pair_upper = pair.upper()
    # Стейбл-стейбл
    stables = ["USDC", "USDT", "DAI", "FRAX", "EURS", "USDS", "PYUSD"]
    stable_count = sum(1 for s in stables if s in pair_upper)
    
    if stable_count >= 2:
        return "stable_stable"
    if stable_count == 1:
        return "stable_major"
        
    # Мейджоры (WETH/WBTC)
    majors = ["ETH", "WETH", "BTC", "WBTC", "SOL"]
    if all(any(m in part for m in majors) for part in pair_upper.split('/')):
        return "major"
        
    return "volatile"

def recommend_fee_tier(
    pair: str,
    strategy: str,
    volatility: float,
    chain: str = "ethereum"
) -> Dict:
    """
    Рекомендует оптимальный fee tier.
    """
    pair_type = classify_pair_type(pair)
    recommendations = []
    rationale = []

    # 1. Логика по типу пары
    if pair_type == "stable_stable":
        recommendations.append(0.01)
        recommendations.append(0.05)
        rationale.append(f"Пара {pair} состоит из стейблкоинов. Низкий тир 0.01% или 0.05% обеспечивает конкурентный спред.")
    elif pair_type == "stable_major":
        recommendations.append(0.05)
        recommendations.append(0.30)
        rationale.append(f"Стандарт для пар Stable/Major — 0.05% (для объема) или 0.3% (для доходности).")
    elif pair_type == "major":
        recommendations.append(0.30)
        recommendations.append(0.05)
        rationale.append(f"Для основных пар (ETH, BTC) тир 0.3% является золотым стандартом Uniswap V3.")
    else:
        recommendations.append(1.00)
        recommendations.append(0.30)
        rationale.append(f"Для волатильных активов тир 1% помогает компенсировать риск IL.")

    # 2. Логика по волатильности
    if volatility < 25:
        recommendations.append(0.05)
        rationale.append(f"Низкая волатильность ({volatility:.0f}%) позволяет конкурировать в тире 0.05%.")
    elif 25 <= volatility <= 80:
        recommendations.append(0.30)
        rationale.append(f"Умеренная волатильность ({volatility:.0f}%) — оптимально 0.3%.")
    else:
        recommendations.append(1.00)
        rationale.append(f"Высокая волатильность ({volatility:.0f}%) требует тира 1% для защиты капитала.")

    # 3. Логика по стратегии
    if strategy == "passive":
        recommendations.append(0.05)
        recommendations.append(0.30)
        rationale.append("Пассивная стратегия (широкий диапазон) эффективнее в тирах с большими объемами (0.05%/0.3%).")
    elif strategy == "active":
        recommendations.append(0.30)
        recommendations.append(1.00)
        rationale.append("Активная стратегия (узкий диапазон) требует более высоких комиссий (0.3%/1.0%) для компенсации частых ребалансировок.")

    # Выбор самого частотного тира
    from collections import Counter
    if not recommendations:
        primary_tier = 0.3 # fallback
    else:
        counts = Counter(recommendations)
        primary_tier = counts.most_common(1)[0][0]

    return {
        "primary_tier": primary_tier,
        "primary_tier_name": FEE_TIERS[primary_tier]["name"],
        "primary_tier_description": FEE_TIERS[primary_tier]["description"],
        "alternatives": [t for t in set(recommendations) if t != primary_tier],
        "rationale": " ".join(dict.fromkeys(rationale)), # убираем дубли сохраняя порядок
        "all_tiers_data": {
            t: {
                "name": d["name"],
                "description": d["description"]
            } for t, d in FEE_TIERS.items()
        }
    }
