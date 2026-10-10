"""Read-only medium-term investment research. No trading or fabricated quotes."""
import os
import json
import gzip
import urllib.parse
import urllib.request
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from functools import lru_cache
from concurrent.futures import ThreadPoolExecutor
from .stock_universe import NIFTY_200

SYMBOLS = ("POLYCAB", "LT", "COROMANDEL", "BEL", "APLAPOLLO",
           "MAXHEALTH", "M&M", "CUMMINSIND", "DALBHARAT", "BDL")
IST = ZoneInfo("Asia/Kolkata")

def ema(values, n):
    if len(values) < n:
        return None
    avg = sum(values[:n]) / n
    for x in values[n:]:
        avg = x * (2 / (n + 1)) + avg * (1 - 2 / (n + 1))
    return avg

def rsi(values, n=14):
    if len(values) <= n:
        return None
    diffs = [values[i] - values[i - 1] for i in range(1, len(values))]
    gains = [max(d, 0) for d in diffs]
    losses = [max(-d, 0) for d in diffs]
    up, down = sum(gains[:n]) / n, sum(losses[:n]) / n
    for g, l in zip(gains[n:], losses[n:]):
        up = (up * (n - 1) + g) / n
        down = (down * (n - 1) + l) / n
    if down == 0:
        return 50 if up == 0 else 100
    return 100 - 100 / (1 + up / down)

@lru_cache(maxsize=1)
def nse_equity_keys():
    url = "https://assets.upstox.com/market-quote/instruments/exchange/NSE.json.gz"
    request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(request, timeout=20) as response:
        instruments = json.loads(gzip.decompress(response.read()))
    return {row["trading_symbol"]: row["instrument_key"] for row in instruments
            if row.get("instrument_type") == "EQ"
            and row.get("segment") == "NSE_EQ"}

def candles_for(symbol, end):
    token = os.getenv("UPSTOX_ACCESS_TOKEN", "").strip()
    if not token:
        raise RuntimeError("Upstox access token not configured")
    key = NIFTY_200.get(symbol)
    if not key:
        key = nse_equity_keys().get(symbol)
    if not key:
        raise LookupError("Instrument unavailable in NIFTY_200 universe")
    start = end - timedelta(days=430)
    encoded = urllib.parse.quote(key, safe="")
    url = f"https://api.upstox.com/v3/historical-candle/{encoded}/days/1/{end}/{start}"
    request = urllib.request.Request(url, headers={
        "Authorization": "Bearer " + token, "Accept": "application/json"})
    with urllib.request.urlopen(request, timeout=12) as response:
        payload = json.load(response)
    raw = payload.get("data", {}).get("candles", [])
    if not raw:
        raise ValueError("No Upstox daily candles")
    completed = [row for row in raw if datetime.fromisoformat(row[0]).date() <= end]
    if not completed:
        raise ValueError("No completed daily candles")
    return sorted(completed, key=lambda x: x[0])

def analyze(symbol, end):
    rows = candles_for(symbol, end)
    closes = [float(x[4]) for x in rows]
    volumes = [float(x[5]) for x in rows]
    last = rows[-1]
    if len(rows) < 100:
        raise ValueError("Insufficient history for weekly trend")
    if (end - datetime.fromisoformat(last[0]).date()).days > 7:
        raise ValueError("Stale historical candles")
    price = closes[-1]
    e20, e50 = ema(closes, 20), ema(closes, 50)
    weekly = {}
    for row in rows:
        day = datetime.fromisoformat(row[0]).date()
        weekly[day.isocalendar()[:2]] = float(row[4])
    # Do not use an unfinished trading week as a completed weekly signal.
    last_day = datetime.fromisoformat(last[0]).date()
    if last_day.weekday() < 4:
        weekly.pop(last_day.isocalendar()[:2], None)
    e20w = ema(list(weekly.values()), 20)
    strength = rsi(closes)
    volume_ratio = (volumes[-1] / (sum(volumes[-21:-1]) / 20)
                    if len(volumes) >= 21 and sum(volumes[-21:-1]) > 0 else None)
    macd = None
    if len(closes) >= 35:
        macd_series = [ema(closes[:i], 12) - ema(closes[:i], 26)
                       for i in range(26, len(closes) + 1)]
        signal = ema(macd_series, 9)
        macd = {"line": round(macd_series[-1], 2),
                "signal": round(signal, 2) if signal is not None else None,
                "bullish": signal is not None and macd_series[-1] > signal}
    bullish = (e20 is not None and e50 is not None and e20w is not None
               and price > e20 > e50 and price > e20w
               and strength is not None and 50 <= strength <= 75
               and volume_ratio is not None and volume_ratio >= 1.5
               and macd is not None and macd["bullish"])
    developing = (e20 is not None and price > e20
                  and strength is not None and strength >= 45)
    return {
        "symbol": symbol, "price": round(price, 2),
        "candle_at": last[0], "source": "Upstox historical daily candle",
        "quote_type": "DAILY_CLOSE_NOT_LIVE",
        "ema20": round(e20, 2) if e20 is not None else None,
        "ema50": round(e50, 2) if e50 is not None else None,
        "weekly_ema20": round(e20w, 2) if e20w is not None else None,
        "rsi14": round(strength, 1) if strength is not None else None,
        "relative_volume": round(volume_ratio, 2) if volume_ratio is not None else None,
        "macd": macd,
        "status": "TECHNICAL_SCREEN_PASSED" if bullish else
                  "REVERSAL_DEVELOPING" if developing else "WATCH",
        "note": "Screening only; verify trend, fundamentals, candle completion and entry before trading."
    }

@lru_cache(maxsize=4)
def cached_snapshot(bucket):
    now = datetime.now(IST)
    # Historical API can include today's unfinished candle. Exclude it during the session.
    end = now.date()
    if now.weekday() < 5 and (now.hour, now.minute) < (15, 45):
        end -= timedelta(days=1)
    while end.weekday() >= 5:
        end -= timedelta(days=1)
    def safe_analyze(symbol):
        try:
            return analyze(symbol, end)
        except Exception as exc:
            return {"symbol": symbol, "status": "DATA_UNAVAILABLE",
                    "error": type(exc).__name__, "price": None}
    # Limit parallel requests so one slow instrument does not block all others.
    with ThreadPoolExecutor(max_workers=4) as pool:
        output = list(pool.map(safe_analyze, SYMBOLS))
    return {"as_of_ist": now.isoformat(), "timeframe": "daily/weekly",
            "data_is_live": False, "risk_per_trade_inr": 2500,
            "stocks": output}
