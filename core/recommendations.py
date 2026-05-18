from core.il_calculator import calculate_il
from data.price_client import get_historical_prices
from core.gas_estimator import estimate_rebalance_gas_usd

def get_recommendation(position: dict, current_price: float, fees_token0: float, fees_token1: float, settings: dict) -> dict:
    """
    Рассчитывает рекомендацию для позиции.
    Возвращает: {"action": "HOLD"|"WAIT"|"REBALANCE"|"REINVEST"|"BUY_ASSET"|"TAKE_PROFIT", "message": str, "priority": "low"|"medium"|"high"}
    """
    lower_price = position.get("lower_price", 0.0)
    upper_price = position.get("upper_price", 0.0)
    token0_amount = position.get("token0_amount", 0.0)
    token1_amount = position.get("token1_amount", 0.0)
    pair = position.get("pair", "")
    
    # Стейблы для упрощения
    t1_price = 1.0 # предполагаем, что token1 - стейбл
    t0_price = current_price
    
    # 1. Стоимость позиции и комиссий
    value = token0_amount * t0_price + token1_amount * t1_price
    fees_total = fees_token0 * t0_price + fees_token1 * t1_price
    
    # 2. IL расчет
    il_percent, il_dollar, current_value = calculate_il(
        current_price=current_price,
        lower_price=lower_price,
        upper_price=upper_price,
        initial_token0=token0_amount,
        initial_token1=token1_amount
    )
    
    # 3. Признак выхода из диапазона
    out_of_range = current_price < lower_price or current_price > upper_price

    # Логика правил
    # Правило 1: Реинвестирование (если комиссии превысили процент от депозита)
    if value > 0 and fees_total > value * (settings.get("fees_reinvest_percent", 10.0) / 100.0):
        return {
            "action": "REINVEST", 
            "message": f"Накоплено ${fees_total:.2f} комиссий. Реинвестируй в расширение диапазона.", 
            "priority": "high"
        }
        
    # Правило 2: Критический IL и достаточные комиссии для покрытия половины
    if il_percent < -settings.get("il_critical_percent", 5.0) and fees_total > abs(il_dollar) * 0.5:
        # Учет ГАЗА
        gas_cost = estimate_rebalance_gas_usd(position.get("network", "ethereum"))
        if gas_cost > fees_total * 0.5:
            return {
                "action": "WAIT",
                "message": f"IL критический, но газ (${gas_cost:.0f}) слишком высок относительно прибыли. Жди.",
                "priority": "medium"
            }
            
        return {
            "action": "REBALANCE",
            "message": f"IL критический ({il_percent:.1f}%). Рекомендуется ребалансировка (газ ~${gas_cost:.1f}).",
            "priority": "high"
        }
        
    # Правило 3: Превышен Warning IL, но комиссии малы
    if il_percent < -settings.get("il_warning_percent", 3.0) and fees_total < abs(il_dollar) * 0.8:
        return {
            "action": "WAIT",
            "message": f"IL {il_percent:.1f}% превышает комиссии. Не ребалансируй, копи комиссии.",
            "priority": "medium"
        }

    # Правило 4: Вне диапазона без сильного IL
    if out_of_range and il_percent > -settings.get("il_warning_percent", 3.0):
        return {
            "action": "HOLD",
            "message": "Цена вне диапазона, но IL низкий. Жди возврата.",
            "priority": "low"
        }
        
    # Правило 5 и 6: Тренд за 7 дней (только если есть данные)
    try:
        base_symbol = pair.split('/')[0] if '/' in pair else pair
        hist_prices = get_historical_prices(base_symbol, days=7)
        if hist_prices and len(hist_prices) > 0:
            price_7d_ago = hist_prices[0]
            if price_7d_ago > 0:
                change = (current_price - price_7d_ago) / price_7d_ago * 100.0
                if change < -10.0:
                    return {
                        "action": "BUY_ASSET",
                        "message": f"Цена упала на {abs(change):.1f}%. Конвертируй комиссии в актив для усреднения.",
                        "priority": "medium"
                    }
                elif change > 10.0:
                    return {
                        "action": "TAKE_PROFIT",
                        "message": f"Цена выросла на {change:.1f}%. Фиксируй комиссии в стейблы.",
                        "priority": "medium"
                    }
    except Exception as e:
        # st.error(f"Ошибка получения цен за 7 дней: {e}")
        pass

    # Правило по умолчанию
    return {
        "action": "HOLD",
        "message": "Позиция работает нормально. Продолжай собирать комиссии.",
        "priority": "low"
    }

