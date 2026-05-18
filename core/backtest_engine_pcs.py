import streamlit as st
from data.pancake_subgraph import fetch_pool_day_data_pcs

class PCSBacktestEngine:
    @staticmethod
    @st.cache_data(ttl=3600, show_spinner=False)
    def calculate_apr(pool_id: str, network: str, lower_price: float, upper_price: float, deposit_usd: float, days: int = 180) -> dict | None:
        daily_data = fetch_pool_day_data_pcs(pool_id, network, days=days)
        if not daily_data or len(daily_data) < 7:
            return None
            
        total_user_fees = 0.0
        days_in_range = 0
        avg_share = 0.0
        
        for day in daily_data:
            low = day.get("low", 0.0)
            high = day.get("high", 0.0)
            tvl_usd = day.get("tvlUSD", 0.0)
            fees_usd = day.get("feesUSD", 0.0)
            
            if tvl_usd <= 0 or fees_usd <= 0:
                continue
                
            # Пересечение: low <= upper and high >= lower
            if low <= upper_price and high >= lower_price:
                time_ratio = 1.0 # Упрощение: если пересекает, то весь день внутри
                share = deposit_usd / tvl_usd
                share = min(share, 0.05) # Ограничиваем долю до 5%
                
                daily_fees = fees_usd * share * time_ratio
                total_user_fees += daily_fees
                days_in_range += 1
                avg_share += share
                
        actual_days = len(daily_data)
        if actual_days == 0:
            return None
            
        if days_in_range > 0:
            avg_share /= days_in_range
            
        apr = (total_user_fees / deposit_usd) * (365 / actual_days) * 100
        
        # Ограничения по ТЗ
        is_anomaly = False
        width_pct = (upper_price - lower_price) / ((lower_price + upper_price) / 2)
        if apr > 35.0 and width_pct > 0.8:
            apr *= 0.8
            is_anomaly = True
            
        apr = max(0.5, min(60.0, apr))
        
        return {
            "apr": apr,
            "total_fees": total_user_fees,
            "days_in_range": days_in_range,
            "avg_share": avg_share,
            "actual_days": actual_days,
            "is_anomaly": is_anomaly
        }
