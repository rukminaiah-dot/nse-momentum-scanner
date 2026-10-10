"""Read-only positional breakout research from completed Yahoo Finance daily candles."""
import json
import math
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from concurrent.futures import ThreadPoolExecutor

def analyze_symbol(symbol, risk_budget=2500, capital=500000):
    ticker = urllib.parse.quote(symbol + ".NS", safe="")
    request = urllib.request.Request(
        "https://query1.finance.yahoo.com/v8/finance/chart/" + ticker + "?range=9mo&interval=1d",
        headers={"User-Agent": "Mozilla/5.0", "Accept": "application/json"})
    with urllib.request.urlopen(request, timeout=12) as response:
        result = json.load(response)["chart"]["result"][0]
    quote = result["indicators"]["quote"][0]
    candles = []
    for i, ts in enumerate(result.get("timestamp") or []):
        try:
            o, h, l, c, v = (quote[k][i] for k in ("open", "high", "low", "close", "volume"))
            if all(isinstance(x, (int, float)) and math.isfinite(x) and x > 0 for x in (o,h,l,c)) and isinstance(v,(int,float)) and v >= 0:
                candles.append((ts, float(h), float(l), float(c), float(v)))
        except (IndexError, TypeError, KeyError):
            continue
    # Exclude today's unfinished candle. Daily candle timestamps are exchange-session dates.
    today = datetime.now(timezone.utc).astimezone(__import__("zoneinfo").ZoneInfo("Asia/Kolkata")).date()
    candles = [x for x in candles if datetime.fromtimestamp(x[0], timezone.utc).astimezone(__import__("zoneinfo").ZoneInfo("Asia/Kolkata")).date() < today]
    if len(candles) < 60:
        raise ValueError("INSUFFICIENT_COMPLETED_DAILY_CANDLES")
    close = candles[-1][3]
    high20 = max(x[1] for x in candles[-21:-1])
    high55 = max(x[1] for x in candles[-56:-1])
    low10 = min(x[2] for x in candles[-11:-1])
    volume_avg = sum(x[4] for x in candles[-21:-1]) / 20
    volume_ratio = candles[-1][4] / volume_avg if volume_avg > 0 else None
    def ema(values, period):
        value = sum(values[:period]) / period
        for price in values[period:]:
            value += (price - value) * 2 / (period + 1)
        return value
    closes = [x[3] for x in candles]
    ema20, ema50 = ema(closes,20), ema(closes,50)
    ranges = [max(candles[i][1]-candles[i][2],abs(candles[i][1]-candles[i-1][3]),abs(candles[i][2]-candles[i-1][3])) for i in range(1,len(candles))]
    atr14 = sum(ranges[-14:])/14
    breakout = close > high20 and volume_ratio is not None and volume_ratio >= 1.5 and close > ema20 > ema50
    near = close >= high20*0.97 and close <= high20 and close > ema50
    status = "BREAKOUT_CONFIRMED" if breakout else "NEAR_BREAKOUT" if near else "NO_CONFIRMED_SETUP"
    # A structural stop can be wider than the risk budget permits; never force a 4-6% stop.
    entry = round(close,2) if breakout else None
    stop = round(min(low10, close-1.5*atr14),2) if breakout else None
    risk = entry-stop if entry is not None else None
    shares = min(int(risk_budget//risk),int(capital//entry)) if risk and risk>0 else None
    return {"symbol":symbol,"status":status,"source":"Yahoo Finance daily OHLCV",
            "quote_type":"COMPLETED_DAILY_CANDLE_NOT_LIVE",
            "candle_date":datetime.fromtimestamp(candles[-1][0],timezone.utc).date().isoformat(),
            "close":round(close,2),"breakout_20d":round(high20,2),"breakout_55d":round(high55,2),
            "ema20":round(ema20,2),"ema50":round(ema50,2),
            "volume_ratio":round(volume_ratio,2) if volume_ratio is not None else None,
            "atr14":round(atr14,2),"entry":entry,"stop":stop,
            "target_2r":round(entry+2*risk,2) if risk and risk>0 else None,
            "target_3r":round(entry+3*risk,2) if risk and risk>0 else None,
            "shares_at_risk_budget":shares,"risk_budget_inr":risk_budget,
            "note":"Indicative technical setup only; confirm candle and liquidity. Stops may gap."}

def analyze_watchlist(symbols):
    def safe(symbol):
        try:
            return analyze_symbol(symbol)
        except Exception as exc:
            return {"symbol":symbol,"status":"DATA_UNAVAILABLE","error":type(exc).__name__,
                    "entry":None,"stop":None,"target_2r":None,"target_3r":None}
    with ThreadPoolExecutor(max_workers=5) as pool:
        return list(pool.map(safe,symbols))
