import requests

headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) LLC/2.0"
}

url = "https://omni.icarus.tools/arbitrum"
payload = {
    "jsonrpc": "2.0",
    "method": "cush_ohlcv",
    "params": ["0xc6962004f452be9203591991d15f6b388e09e8d0", 86400000, 1700000000000, 1710000000000],
    "id": 1
}

r = requests.post(url, json=payload, headers=headers)
data = r.json()
print("Result type:", type(data.get("result")))
if data.get("result"):
    first = data["result"][0] if isinstance(data["result"], list) else data["result"]
    print("First item:", first)
else:
    print("No result, raw:", data)
