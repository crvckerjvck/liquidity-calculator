import requests
import streamlit as st
import math
from typing import Optional, List

COINGECKO_MAP = {
    "ETH": "ethereum",
    "SOL": "solana",
    "AVAX": "avalanche-2",
    "SUI": "sui",
    "APT": "aptos",
    "BTC": "bitcoin"
}

BINANCE_MAP = {
    "ETH": "ETHUSDT",
    "BTC": "BTCUSDT",
    "SOL": "SOLUSDT",
    "AVAX": "AVAXUSDT",
    "SUI": "SUIUSDT",
    "APT": "APTUSDT",
    "MATIC": "MATICUSDT",
    "ARB": "ARBUSDT"
}

@st.cache_data(ttl=60, show_spinner=False)
def get_current_price(symbol: str, network: str = "ethereum") -> Optional[float]:
    """
    Получает текущую цену токена в USD.
    Приоритет: Binance (надёжный) → CoinGecko → DexScreener
    """
    base_symbol = symbol.split('/')[0].upper() if '/' in symbol else symbol.upper()
    
    # 0. Стабильные монеты (fast-path)
    if base_symbol in ['USDC', 'USDT', 'DAI', 'USDE', 'FRAX']:
        return 1.0

    # 1. Binance (самый надёжный источник для крупных токенов)
    binance_sym = BINANCE_MAP.get(base_symbol)
    if binance_sym:
        try:
            r = requests.get(f"https://api.binance.com/api/v3/ticker/price?symbol={binance_sym}", timeout=5)
            if r.status_code == 200:
                return float(r.json()["price"])
        except Exception:
            pass
    
    # 2. CoinGecko
    try:
        cg_id = COINGECKO_MAP.get(base_symbol, base_symbol.lower())
        r = requests.get(
            f"https://api.coingecko.com/api/v3/simple/price?ids={cg_id}&vs_currencies=usd",
            timeout=5
        )
        if r.status_code == 200:
            data = r.json()
            if cg_id in data:
                return float(data[cg_id]["usd"])
    except Exception:
        pass

    # 3. DexScreener last resort
    try:
        r = requests.get(f"https://api.dexscreener.com/latest/dex/search?q={base_symbol}/USDC", timeout=5)
        if r.status_code == 200:
            pairs = r.json().get("pairs", [])
            for p in pairs:
                if p.get("liquidity", {}).get("usd", 0) > 10000 and p.get("priceUsd"):
                    return float(p["priceUsd"])
    except Exception:
        pass
        
    return None



@st.cache_data(ttl=3600, show_spinner=False)
def get_historical_prices(symbol: str, days: int = 30) -> Optional[List[float]]:
    """
    Получает исторические цены за указанное количество дней. 
    Приоритет: Binance (истинные закрытия дневных свечей для точной волатильности), затем CoinGecko.
    """
    base_symbol = symbol.split('/')[0] if '/' in symbol else symbol
    
    # 1. Попытка получить истинные OHLC (дневные закрытия) с Binance
    if base_symbol.upper() in BINANCE_MAP:
        try:
            binance_symbol = BINANCE_MAP[base_symbol.upper()]
            # limit не может быть больше 1000, days обычно 30/90/180
            url = f"https://api.binance.com/api/v3/klines?symbol={binance_symbol}&interval=1d&limit={days}"
            response = requests.get(url)
            response.raise_for_status()
            data = response.json()
            # индекс 4 - это цена закрытия свечи
            closes = [float(kline[4]) for kline in data]
            if len(closes) >= days * 0.9: # Допускаем небольшую нехватку
                return closes
        except Exception:
            # Игнорируем ошибку и идем к CoinGecko
            pass

    # 2. Fallback на CoinGecko (может отдавать усредненные/часовые цены)
    try:
        cg_id = COINGECKO_MAP.get(base_symbol.upper(), base_symbol.lower())
        response = requests.get(f"https://api.coingecko.com/api/v3/coins/{cg_id}/market_chart?vs_currency=usd&days={days}")
        response.raise_for_status()
        data = response.json()
        
        if 'prices' in data:
            # CoinGecko может вернуть не 1 точку в день. Берем как есть, calculate_volatility попытается адаптироваться.
            return [float(p[1]) for p in data['prices']]
            
    except Exception as e:
        st.error(f"Не удалось получить историю цен для {symbol}: {e}")
        
    return None

def calculate_volatility(prices: List[float], days_hint: int = 0) -> float:
    """
    Вычисляет годовую волатильность в процентах на основе списка цен.
    Автоматически определяет периодичность данных (hourly vs daily).
    """
    if not prices or len(prices) < 2:
        return 0.0
        
    # Детектируем периодичность (сколько шагов в году)
    # Если на 1 день приходится больше 12 точек -> считаем часовыми
    # Если дней не передано, пробуем угадать по общему количеству
    points_per_day = 1.0
    if days_hint > 0:
        points_per_day = len(prices) / days_hint
    else:
        # Эвристика: если больше 100 точек, скорее всего это не годовой график дневных свечей, 
        # а месячный часовых
        if len(prices) > 100:
            points_per_day = 24.0
            
    steps_per_year = 365.0 * (24.0 if points_per_day > 12.0 else 1.0)

    # Логарифмические доходности
    returns = []
    for i in range(1, len(prices)):
        if prices[i-1] > 0:
            returns.append(math.log(prices[i] / prices[i-1]))
            
    if len(returns) == 0:
        return 0.0
        
    # Выборочное стандартное отклонение (std)
    mean = sum(returns) / len(returns)
    variance = sum((r - mean) ** 2 for r in returns) / (len(returns) - 1) if len(returns) > 1 else 0
    std_dev = math.sqrt(variance)
    
    # Годовая волатильность: std * sqrt(шагов в году)
    annualized_volatility = std_dev * math.sqrt(steps_per_year) * 100.0
    
    return annualized_volatility
