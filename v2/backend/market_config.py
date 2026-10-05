INDICES = {
    "NIFTY 50": "NSE_INDEX|Nifty 50",
    "BANK NIFTY": "NSE_INDEX|Nifty Bank",
    "SENSEX": "BSE_INDEX|SENSEX",
}

CANDLE_INTERVAL = "1minute"

if __name__ == "__main__":
    for name, key in INDICES.items():
        print(name, "=>", key)
    print("V2_INDEX_CONFIG_OK")
