def ema(values, period):
    if not values: return None
    k = 2 / (period + 1)
    value = float(values[0])
    for price in values[1:]:
        value = float(price) * k + value * (1-k)
    return value

print("V2_INDICATORS_OK")
def vwap(highs, lows, closes, volumes):
    total_volume = sum(volumes)
    if total_volume <= 0:
        return None
    total = sum(
        ((h + l + c) / 3) * v
        for h, l, c, v in zip(highs, lows, closes, volumes)
    )
    return total / total_volume

def momentum(values, bars=5):
    if len(values) <= bars: return None
    return ((values[-1] / values[-1-bars]) - 1) * 100

def relative_volume(volumes, lookback=20):
    if len(volumes) <= lookback: return None
    avg = sum(volumes[-lookback-1:-1]) / lookback
    return volumes[-1] / avg if avg > 0 else None

def atr(highs,lows,closes,period=14):
    if len(closes) <= period: return None
    tr=[max(highs[i]-lows[i],abs(highs[i]-closes[i-1]),abs(lows[i]-closes[i-1])) for i in range(1,len(closes))]
    return sum(tr[-period:])/period
