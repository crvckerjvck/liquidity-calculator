from core.backtest_engine_pcs import PCSBacktestEngine

def get_backtest_apr(pool_id: str, network: str, lower: float, upper: float, deposit: float, fee_tier: float, days: int = 180) -> float | None:
    res = PCSBacktestEngine.calculate_apr(pool_id, network, lower, upper, deposit, days)
    if res:
        return res["apr"]
    return None
