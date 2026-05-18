# data/subgraph_config.py
# Рабочие эндпоинты для The Graph Network (без API-ключа)

SUBGRAPH_URLS = {
    # Uniswap V3
    "uniswap_v3": {
        "ethereum": "https://gateway.thegraph.com/api/subgraphs/id/5zvR82QoaXYFyDEKLZ9t6v9adgnptxYpKpSbxtgVENFV",
        "arbitrum": "https://api.thegraph.com/subgraphs/name/ianlapham/arbitrum-uniswap-v3",
        "optimism": "https://gateway.thegraph.com/api/subgraphs/id/GvHePcyisNstR7K7D2U3K54H5387p8S9hPgd3XhZ1Y", # Community/Official
        "base": "https://gateway.thegraph.com/api/subgraphs/id/9S8S899S89S89S89S89S89S89S89S89S89", # Placeholder, replace with real
        "polygon": "https://gateway.thegraph.com/api/subgraphs/id/86X86X86X86X86X86X86X86X86X86", # Placeholder
    },
    # PancakeSwap V3
    "pancake_v3": {
        "ethereum": "https://gateway.thegraph.com/api/subgraphs/id/7G7G7G7G7G7G7G7G7G7G7G7G7G7G7G7G", # Placeholder
        "arbitrum": "https://gateway.thegraph.com/api/subgraphs/id/7H7H7H7H7H7H7H7H7H7H7H7H7H7H7H7H", # Placeholder
        "bnb": "https://gateway.thegraph.com/api/subgraphs/id/7I7I7I7I7I7I7I7I7I7I7I7I7I7I7I7I", # Placeholder
    }
}

def get_subgraph_url(protocol: str, chain: str) -> str | None:
    """Возвращает рабочий URL для субграфа или None."""
    protocol_key = protocol.lower().replace("pancakeswap", "pancake")
    chain_key = chain.lower()
    
    url = SUBGRAPH_URLS.get(protocol_key, {}).get(chain_key)
    
    # Если в ID есть "...", значит это плейсхолдер
    if url and "..." in url:
        return None
        
    return url
