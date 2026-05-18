import json
import os
from typing import Optional

def calculate_heuristic_apr(
    current_price: float,
    lower_price: float,
    upper_price: float,
    deposit_usd: float = 1000.0,
    pair: str = "ETH/USDC",
    chain: str = "arbitrum",
    pool_tvl: float = 1000000.0,
    volume_24h: float = 100000.0,
    fee_tier_decimal: float = 0.3
) -> float:
    """
    Возвращает оценочный APR в процентах на основе 24h Volume, TVL и ширины диапазона.
    """
    # 1. Base Pool Daily Fees
    pool_tvl = max(10000.0, float(pool_tvl if pool_tvl else 1000000.0))
    volume_24h = max(1000.0, float(volume_24h if volume_24h else 100000.0))
    
    # fee_tier_decimal is percentage (e.g. 0.3 for 0.3%). Decimal rate: 0.3 / 100 = 0.003
    fee_rate = fee_tier_decimal / 100.0 if fee_tier_decimal > 0.0 else 0.003
    daily_fees = volume_24h * fee_rate

    # 2. Capital Efficiency Multiplier for V3 Concentrated Liquidity
    from core.metrics import calculate_capital_efficiency
    eff = calculate_capital_efficiency(current_price, lower_price, upper_price)
    
    # Смягчаем теоретическую эффективность, так как ликвидность пула не распределена равномерно (V2)
    # Большинство TVL пула тоже сконцентрировано вокруг текущей цены.
    relative_eff = max(1.0, (eff ** 0.6))
    
    # 3. User Share & Returns
    effective_deposit = deposit_usd * relative_eff
    share = effective_deposit / pool_tvl
    share = min(0.5, share) # Cap share conceptually
    
    user_daily_fees = daily_fees * share
    
    # Annualize
    apr = (user_daily_fees * 365) / deposit_usd * 100.0
    
    # 4. Impairment / Out_of_bounds discounting
    width_pct = abs(upper_price - lower_price) / current_price
    imp_loss_discount = 1.0
    if width_pct < 0.05:
        imp_loss_discount = 0.3 # Почти всегда вне диапазона
    elif width_pct < 0.15:
        imp_loss_discount = 0.7
        
    apr *= imp_loss_discount

    return min(150.0, max(0.1, round(apr, 1)))
