def estimate_rebalance_gas_usd(network: str, dex: str = "any") -> float:
    """
    Приблизительная оценка стоимости газа для ребалансировки в USD.
    Используется для фильтрации невыгодных рекомендаций.
    """
    network = network.lower()
    
    # Статические оценки (могут быть вынесены в конфиг)
    gas_map = {
        "ethereum": 30.0,
        "arbitrum": 0.5,
        "optimism": 0.5,
        "base": 0.3,
        "polygon": 0.1,
        "bsc": 0.2,
        "bnb": 0.2,
        "solana": 0.01,
        "sui": 0.02,
        "aptos": 0.02,
        "avalanche": 0.5,
        "avax": 0.5
    }
    
    return gas_map.get(network, 1.0) # По умолчанию $1
