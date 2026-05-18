"""
core/backtest.py
Симуляция LP позиции в прошлом на реальных ценах.
"""
import pandas as pd
import math
from core.il_calculator import calculate_il
from data.price_client import get_historical_prices


def run_backtest(
    symbol: str,
    lower_price: float,
    upper_price: float,
    initial_deposit: float = 1000.0,
    days: int = 30,
    fee_tier: float = 0.003,
    avg_volume_24h: float = 1_000_000.0,
    pool_tvl: float = 10_000_000.0,
) -> dict:
    """
    Симулирует работу позиции в прошлом.
    """
    prices = get_historical_prices(symbol, days=days)
    if not prices or len(prices) < 2:
        return {"error": "Недостаточно исторических данных для бэктеста."}

    initial_price = prices[0]
    sqrt_p = math.sqrt(initial_price)
    sqrt_pa = math.sqrt(lower_price)
    sqrt_pb = math.sqrt(upper_price)

    # --- КОРРЕКТНЫЙ РАСЧЕТ НАЧАЛЬНОЙ ЛИКВИДНОСТИ (L) ---
    # Мы не можем просто задать 50/50. В V3 количество токенов жестко привязано к P и [Pa, Pb].
    # Мы вычисляем такое L, чтобы суммарная стоимость x*P + y была равна initial_deposit.
    
    if initial_price <= lower_price:
        # 100% token0
        L = initial_deposit / ((sqrt_pb - sqrt_pa) / (sqrt_pa * sqrt_pb) * initial_price)
        t0_amount = initial_deposit / initial_price
        t1_amount = 0.0
    elif initial_price >= upper_price:
        # 100% token1
        L = initial_deposit / (sqrt_pb - sqrt_pa)
        t0_amount = 0.0
        t1_amount = initial_deposit
    else:
        # Mixed tokens
        # Formula: Deposit = L * ( (sqrt(Pb)-sqrt(P))/(sqrt(P)*sqrt(Pb)) * P + (sqrt(P)-sqrt(Pa)) )
        # Simplified: Deposit = L * ( sqrt(P) - P/sqrt(Pb) + sqrt(P) - sqrt(Pa) )
        # L = Deposit / (2*sqrt(P) - P/sqrt(Pb) - sqrt(Pa))
        denom = (2 * sqrt_p) - (initial_price / sqrt_pb) - sqrt_pa
        L = initial_deposit / denom if denom > 0 else 0.0
        t0_amount = L * (sqrt_pb - sqrt_p) / (sqrt_p * sqrt_pb)
        t1_amount = L * (sqrt_p - sqrt_pa)

    # Доля в пуле
    pool_tvl_safe = max(pool_tvl, initial_deposit, 1.0)
    our_share = initial_deposit / pool_tvl_safe

    results = []
    total_fees_usd = 0.0

    for i, p in enumerate(prices):
        # Текущая стоимость позиции с учётом IL
        # Используем те же t0_amount и t1_amount которые мы "купили" на старте
        il_perc, il_usd, current_val = calculate_il(
            current_price=p,
            lower_price=lower_price,
            upper_price=upper_price,
            initial_token0=t0_amount,
            initial_token1=t1_amount,
            initial_price=initial_price,
        )

        # HODL Value (if we just kept the initial tokens)
        hold_val = t0_amount * p + t1_amount
        
        # Комиссии
        in_range = lower_price <= p <= upper_price
        daily_fee = 0.0
        if in_range and avg_volume_24h > 0:
            daily_fee = avg_volume_24h * fee_tier * our_share
            total_fees_usd += daily_fee

        results.append({
            "day": i,
            "price": p,
            "value_hold": round(hold_val, 4),
            "value_pool_no_fees": round(current_val, 4),
            "daily_fee": round(daily_fee, 4),
            "cumulative_fees": round(total_fees_usd, 4),
            "total_value": round(current_val + total_fees_usd, 4),
            "in_range": in_range,
        })

    df = pd.DataFrame(results)

    final_row = df.iloc[-1]
    final_val = final_row["total_value"]
    hold_val = final_row["value_hold"]
    pool_val_no_fees = final_row["value_pool_no_fees"]
    
    net_pnl = final_val - initial_deposit
    net_pnl_perc = (net_pnl / initial_deposit) * 100.0
    
    # Расщепление PnL
    hodl_pnl = hold_val - initial_deposit
    il_vs_hodl = pool_val_no_fees - hold_val
    
    days_in_range = int(df["in_range"].sum())
    range_utilization = (days_in_range / len(prices)) * 100.0

    return {
        "df": df,
        "final_value": final_val,
        "hold_value": hold_val,
        "total_fees": total_fees_usd,
        "net_pnl_usd": net_pnl,
        "net_pnl_perc": net_pnl_perc,
        "hodl_pnl_usd": hodl_pnl,
        "il_usd": il_vs_hodl,
        "range_utilization": range_utilization,
        "days": len(prices),
        "our_share_pct": our_share * 100,
    }
