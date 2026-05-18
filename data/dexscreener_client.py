import requests
import streamlit as st

@st.cache_data(ttl=300, show_spinner=False)
def get_pool_info(pair_symbol: str, network: str = "ethereum") -> dict | None:
    """
    Получает информацию о пуле (объем, ликвидность) из DexScreener.
    pair_symbol: "ETH/USDC"
    network: "ethereum", "arbitrum", и т.д.
    """
    # Уточняем поиск для лучшего соответствия Uniswap V3
    # Уточняем поиск для лучшего соответствия Uniswap V3
    search_query = f"{pair_symbol} uniswap v3 {network}"
    url = f"https://api.dexscreener.com/latest/dex/search?q={search_query}"
    
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        data = response.json()
        
        pairs = data.get("pairs", [])
        if not pairs:
            # Fallback to general search if specific fails
            url_fallback = f"https://api.dexscreener.com/latest/dex/search?q={pair_symbol}"
            response = requests.get(url_fallback, timeout=10)
            data = response.json()
            pairs = data.get("pairs", [])
            
        if not pairs:
            return None
            
        # Символы для фильтрации (точное совпадение)
        base_target = pair_symbol.split('/')[0].upper()
        quote_target = pair_symbol.split('/')[1].upper() if '/' in pair_symbol else "USDC"
            
        # Фильтруем по сети и символам
        filtered_pairs = []
        for p in pairs:
            # 1. Проверка адреса (только 20 байт / 42 символа с 0x)
            addr = p.get("pairAddress", "")
            if len(addr) != 42:
                continue # Пропускаем Uniswap V4 (64 символа) и прочие нестандартные ID
            
            # 2. Проверка сети
            chain_match = p.get("chainId") == network or network in p.get("url", "").lower()
            if not chain_match:
                continue
            
            # 3. Проверка символов
            p_base = p.get("baseToken", {}).get("symbol", "").upper()
            p_quote = p.get("quoteToken", {}).get("symbol", "").upper()
            
            symbol_match = (p_base == base_target or p_base == f"{base_target}.E" or base_target == f"{p_base}.E") and \
                           (p_quote == quote_target or p_quote == f"{quote_target}.E" or quote_target == f"{p_quote}.E")
            
            if symbol_match:
                filtered_pairs.append(p)
                
        if not filtered_pairs:
            filtered_pairs = [p for p in pairs if p.get("chainId") == network and len(p.get("pairAddress", "")) == 42]
            if not filtered_pairs: filtered_pairs = pairs
            
        # Сортировка: приоритет Uniswap V3 + Объем + Ликвидность
        def pool_rank(p):
            dex_id = p.get("dexId", "").lower()
            rank = 0
            if "uniswap" in dex_id:
                if "v3" in dex_id:
                    rank = 100
                else:
                    rank = 50
            elif "pancakeswap" in dex_id:
                rank = 20
                
            # Приоритет объему (если объем > 1000$ - это живой пул)
            vol_24h = float(p.get("volume", {}).get("h24", 0))
            is_alive = 1 if vol_24h > 1000 else 0
            
            liquidity = float(p.get("liquidity", {}).get("usd", 0))
            
            # (Rank, Живой, Объем, Ликвидность)
            return (rank, is_alive, vol_24h, liquidity)
            
        best_pair = max(filtered_pairs, key=pool_rank)
        print(f"[DEX] Selected pool {best_pair.get('pairAddress')} on {best_pair.get('dexId')} (Vol: {best_pair.get('volume', {}).get('h24')}, Rank: {pool_rank(best_pair)[0]})")
        
        return {
            "dex_id": best_pair.get("dexId"),
            "pair_address": best_pair.get("pairAddress"),
            "price_usd": float(best_pair.get("priceUsd", 0)),
            "volume_24h": float(best_pair.get("volume", {}).get("h24", 0)),
            "liquidity_usd": float(best_pair.get("liquidity", {}).get("usd", 0)),
            "pair_url": best_pair.get("url")
        }
    except Exception as e:
        print(f"Error fetching DexScreener pool info: {e}")
        return None
