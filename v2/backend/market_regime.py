def index_signal(price, ema9, ema20, vwap):
    if None in (price, ema9, ema20, vwap): return "NEUTRAL"
    if price > vwap and ema9 > ema20: return "BULLISH"
    if price < vwap and ema9 < ema20: return "BEARISH"
    return "NEUTRAL"

print("V2_MARKET_REGIME_OK")
