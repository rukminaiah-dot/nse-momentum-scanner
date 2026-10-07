def index_signal(price, ema9, ema20, vwap):
    if None in (price, ema9, ema20): return "NEUTRAL"
    if ema9 > ema20 and (vwap is None or price > vwap): return "BULLISH"
    if ema9 < ema20 and (vwap is None or price < vwap): return "BEARISH"
    return "NEUTRAL"

print("V2_MARKET_REGIME_OK")
