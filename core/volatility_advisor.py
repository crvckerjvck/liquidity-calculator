import json
import os
from data.price_client import get_historical_prices, calculate_volatility

def load_absolute_min_widths() -> dict:
    try:
        config_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'config', 'absolute_min_widths.json')
        with open(config_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return {}

def get_recommended_min_width(symbol: str, current_price: float) -> float:
    base_symbol = symbol.split('/')[0] if '/' in symbol else symbol
    
    historical_prices = get_historical_prices(base_symbol)
    if not historical_prices or len(historical_prices) < 2:
        recommended = current_price * 0.25
    else:
        vol = calculate_volatility(historical_prices) / 100.0
        # Ограничиваем волатильность диапазоном 0.2 - 1.5
        vol = max(0.2, min(vol, 1.5))
        recommended = current_price * max(0.25, vol)
        
    abs_mins = load_absolute_min_widths()
    absolute_min = abs_mins.get(base_symbol.upper(), current_price * 0.25)
    
    return max(recommended, absolute_min)

def check_range_too_narrow(symbol: str, current_price: float, lower_price: float, upper_price: float) -> tuple[bool, str]:
    recommended = get_recommended_min_width(symbol, current_price)
    current_width = upper_price - lower_price
    
    if current_width < recommended * 0.9:
        return (True, f"⚠️ Диапазон слишком узкий. Рекомендуемая минимальная ширина: ${recommended:.0f}. Текущая ширина: ${current_width:.0f}.")
    return (False, "Диапазон в порядке.")
