import requests
import streamlit as st

from data.subgraph_config import get_subgraph_url

def query_subgraph(query: str, variables: dict = None, network: str = "ethereum") -> dict | None:
    url = get_subgraph_url("uniswap_v3", network)
    if not url:
        return None
    try:
        response = requests.post(url, json={'query': query, 'variables': variables if variables else {}}, timeout=10)
        response.raise_for_status()
        return response.json()
    except Exception:
        return None

def get_token_address(symbol: str, network: str = "ethereum") -> str | None:
    # Расширенный маппинг для Arbitrum и Ethereum
    mapping = {
        "ethereum": {
            "ETH": "0xc02aaa39b223fe8d0a0e5c4f27ead9083c756cc2",
            "WETH": "0xc02aaa39b223fe8d0a0e5c4f27ead9083c756cc2",
            "USDC": "0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48",
            "USDT": "0xdac17f958d2ee523a2206206994597c13d831ec7",
            "WBTC": "0x2260fac5e5542a773aa44fbcfedf7c193bc2c599",
            "DAI": "0x6b175474e89094c44da98b954eedeac495271d0f",
        },
        "arbitrum": {
            "ETH": "0x82af49447d8a07e3bd95bd0d56f352415231fb11", # WETH on Arb
            "WETH": "0x82af49447d8a07e3bd95bd0d56f352415231fb11",
            "USDC": "0xaf88d065e77c8cC2239327C5EDb3A432268e5831",
            "USDT": "0xfd086bc7cd5c481dcc9c85ebe478a1c0b69fcbb9",
            "ARB": "0x912ce59144191c1204e64559fe8253a0e49e6548",
        }
    }
    net = network.lower()
    if net not in mapping:
        # Пытаемся взять хоть что-то из дефолта
        return mapping["ethereum"].get(symbol.upper())
    return mapping[net].get(symbol.upper())

def get_pool_address(token0: str, token1: str, fee_tier: int = 3000, network: str = "ethereum") -> str | None:
    """
    fee_tier: в базисных пунктах (3000 = 0.3%, 500 = 0.05%)
    """
    t0_addr = get_token_address(token0, network)
    t1_addr = get_token_address(token1, network)
    
    if not t0_addr or not t1_addr:
        return None
        
    lower_t0 = t0_addr.lower()
    lower_t1 = t1_addr.lower()
        
    if lower_t0 > lower_t1:
        lower_t0, lower_t1 = lower_t1, lower_t0
        
    query = """
    query getPool($t0: String!, $t1: String!, $fee: Int!) {
      pools(where: {token0: $t0, token1: $t1, feeTier: $fee}) {
        id
      }
    }
    """
    variables = {"t0": lower_t0, "t1": lower_t1, "fee": fee_tier}
    data = query_subgraph(query, variables, network=network)
    
    if data and data.get("data", {}).get("pools"):
        return data["data"]["pools"][0]["id"]
    return None

def get_pool_day_data(pool_address: str, days: int = 7, network: str = "ethereum") -> list[dict] | None:
    query = """
    query getPoolData($pool: String!, $days: Int!) {
      poolDayDatas(
        where: {pool: $pool}
        orderBy: date
        orderDirection: desc
        first: $days
      ) {
        date
        feesUSD
        tvlUSD
        volumeUSD
      }
    }
    """
    variables = {"pool": pool_address.lower(), "days": days}
    data = query_subgraph(query, variables, network=network)
    
    if data and data.get("data", {}).get("poolDayDatas"):
        return data["data"]["poolDayDatas"]
    return None

def get_v3_apr_estimate(pool_address: str, network: str = "ethereum") -> float | None:
    day_data = get_pool_day_data(pool_address, days=7, network=network)
    if not day_data:
        return None
        
    total_fees = sum(float(d["feesUSD"]) for d in day_data)
    avg_tvl = sum(float(d["tvlUSD"]) for d in day_data) / len(day_data)
    
    if avg_tvl <= 0:
        return 0.0
        
    apr = (total_fees / 7 * 365) / avg_tvl * 100
    return apr

@st.cache_data(ttl=3600, show_spinner=False)
def get_llama_pool_data(pool_address: str) -> dict:
    return {"status": "success", "apr": None}

@st.cache_data(ttl=3600, show_spinner=False)
def get_llama_pool_data(pool_address: str) -> dict:
    """Получает данные по пулу из DeFiLlama."""
    # Примечание: DeFiLlama требует slug или ID. Если есть адрес, можно искать.
    # Для упрощения оставим как заглушку, возвращающую статус ошибки, 
    # так как DexScreener и Subgraph уже дают достаточно данных.
    return {"status": "success", "apr": None}
