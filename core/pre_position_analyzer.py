import numpy as np
from core.metrics import calculate_apr, calculate_capital_efficiency, get_historical_vol_metrics
from core.apr_estimator import estimate_realistic_apr
from core.fee_tier_recommender import recommend_fee_tier
from data.price_client import get_historical_prices, get_current_price
from data.dexscreener_client import get_pool_info
from data.revert_client import get_pool_address
from data.subgraph_config import get_subgraph_url

def analyze_pair(
    pair: str, 
    network: str = "ethereum", 
    strategy: str = "balanced", 
    deposit_usd: float = 1000.0,
    goal: str = "reinvest"
) -> dict:
    """
    Анализирует пару и возвращает рекомендации по диапазонам.
    strategy: "passive" (180d) / "active" (30d) / "balanced" (90d)
    """
    base_symbol = pair.split('/')[0] if '/' in pair else pair
    subgraph_failed = False
    
    # 1. Данные по цене (Декуплируем цену токена от цены пула для стабильности)
    current_price = get_current_price(base_symbol, network)
    
    # 2. Данные по пулу
    pool_info = get_pool_info(pair, network)
    if not pool_info:
        return {"error": "Не удалось получить данные о пуле для этой пары."}
        
    if current_price is None or current_price == 0:
        current_price = float(pool_info.get("price_usd", 0))
        
    volume_24h = pool_info.get("volume_24h", 0)
    liquidity_usd = pool_info.get("liquidity_usd", 0)
    
    # 3. Волатильность и экстремумы
    window_map = {"passive": 180, "active": 30, "balanced": 90}
    days = window_map.get(strategy, 90)
    vol_data_full = get_historical_vol_metrics(base_symbol, windows=[30, 90, 180])
    
    # Если текущая цена всё еще 0, попробуем взять её из исторических данных
    if (current_price is None or current_price == 0) and vol_data_full:
        for d in [30, 90, 180]:
            if d in vol_data_full and vol_data_full[d].get("max", 0) > 0:
                # Эвристика: среднее между min/max или просто min/max как ориентир
                current_price = (vol_data_full[d]["min"] + vol_data_full[d]["max"]) / 2
                break

    if not current_price or current_price == 0:
        return {"error": f"Не удалось определить цену для {base_symbol}. Попробуйте позже."}

    current_metrics = vol_data_full.get(days, {"volatility": 50.0, "min": current_price*0.8, "max": current_price*1.2})
    vol_annual = current_metrics["volatility"] / 100.0
    hist_min = current_metrics["min"]
    hist_max = current_metrics["max"]
    
    # 3. Исторические цены для расчета риска (используем для волл-бэка)
    hist_prices = get_historical_prices(base_symbol, days=days)
    
    # 4. Расчет вариантов (Conservative, Balanced, Aggressive)
    if strategy == "passive":
        base_width_perc = max(0.5, vol_annual * 1.5)
    elif strategy == "active":
        base_width_perc = max(0.1, vol_annual * 0.5)
    else: # balanced
        base_width_perc = max(0.25, vol_annual * 1.0)
        
    goal_map = {"accumulation": 1.2, "cashflow": 0.8, "reinvest": 1.0, "hybrid_50_50": 0.9}
    base_width_perc *= goal_map.get(goal, 1.0)
        
    suggestions = []
    tiers = [
        {"type": "conservative", "mult": 1.5},
        {"type": "balanced", "mult": 1.0},
        {"type": "aggressive", "mult": 0.5}
    ]
    
    for tier in tiers:
        # Для Conservative пробуем расширить до исторических границ, если они шире
        if tier["type"] == "conservative":
            # Расчетная ширина
            calc_width = base_width_perc * tier["mult"]
            calc_lower = current_price * (1 - calc_width / 2)
            calc_upper = current_price * (1 + calc_width / 2)
            
            # Историческая ширина + 5% запас (safety margin)
            safe_lower = hist_min * 0.95
            safe_upper = hist_max * 1.05
            
            # Выбираем наиболее безопасный (широкий) вариант
            lower = min(calc_lower, safe_lower)
            upper = max(calc_upper, safe_upper)
            width_perc = (upper - lower) / current_price 
        else:
            width_perc = base_width_perc * tier["mult"]
            lower = current_price * (1 - width_perc / 2)
            upper = current_price * (1 + width_perc / 2)
        
        lower = max(0.000001, lower)
        
        # Риск выхода
        risk_score = 0
        if hist_prices:
            outside_count = sum(1 for p in hist_prices if p < lower or p > upper)
            risk_score = (outside_count / len(hist_prices)) * 100.0
            
        eff = calculate_capital_efficiency(current_price, lower, upper)
        tier_rec = recommend_fee_tier(pair, strategy, current_metrics["volatility"], network)
        fee_tier = tier_rec["primary_tier"]
        
        concentrated_apr = None
        debug_info = None
        source_label = "Эвристическая модель"
        
        # Используем эвристическую модель для расчета APR (Этап 28)
        
        from core.heuristic_apr import calculate_heuristic_apr
        concentrated_apr = calculate_heuristic_apr(
            current_price=current_price,
            lower_price=lower,
            upper_price=upper,
            deposit_usd=deposit_usd,
            pair=pair,
            chain=network,
            pool_tvl=liquidity_usd,
            volume_24h=volume_24h,
            fee_tier_decimal=fee_tier
        )
        
        suggestions.append({
            "type": tier["type"],
            "lower": lower,
            "upper": upper,
            "width_perc": width_perc * 100,
            "expected_apr": concentrated_apr,
            "risk_score": risk_score,
            "fee_tier": fee_tier,
            "efficiency": eff,
            "source": source_label,
            "fee_tier_rationale": tier_rec["rationale"],
            "fee_tier_alternatives": tier_rec["alternatives"],
            "debug_info": debug_info
        })
        
    return {
        "current_price": current_price,
        "volatility_annual": vol_annual * 100,
        "volume_24h": volume_24h,
        "liquidity_usd": liquidity_usd,
        "historical_min": hist_min,
        "historical_max": hist_max,
        "history_days": days,
        "suggestions": suggestions,
        "subgraph_failed": subgraph_failed
    }
