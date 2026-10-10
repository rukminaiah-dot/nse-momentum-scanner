"""Isolated, read-only preview service. Does not import the trading API."""
import json
import os
import urllib.request
import urllib.error
import urllib.parse
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from datetime import datetime
from zoneinfo import ZoneInfo
from v2.backend.investment import cached_snapshot, SYMBOLS, NIFTY_200, nse_equity_keys
from v2.backend.positional_breakouts import analyze_watchlist
from functools import lru_cache

def direct_upstox_quotes():
    """Read-only fallback: one Upstox V3 request for the ten watchlist symbols."""
    token = os.getenv("UPSTOX_ACCESS_TOKEN", "").strip()
    if not token:
        raise RuntimeError("UPSTOX_ACCESS_TOKEN_NOT_CONFIGURED")
    missing = [symbol for symbol in SYMBOLS if symbol not in NIFTY_200]
    try:
        extra = nse_equity_keys() if missing else {}
    except urllib.error.HTTPError as exc:
        print("UPSTOX_INSTRUMENT_DOWNLOAD_FAILURE:", exc.code, flush=True)
        raise
    keys = {symbol: NIFTY_200.get(symbol) or extra.get(symbol) for symbol in SYMBOLS}
    if any(not key for key in keys.values()):
        raise LookupError("WATCHLIST_INSTRUMENT_KEY_MISSING")
    query = urllib.parse.urlencode({"instrument_key": ",".join(keys.values())})
    request = urllib.request.Request(
        "https://api.upstox.com/v3/market-quote/ltp?" + query,
        headers={"Accept": "application/json", "Authorization": "Bearer " + token})
    try:
        with urllib.request.urlopen(request, timeout=18) as response:
            payload = json.load(response)
    except urllib.error.HTTPError as exc:
        print("UPSTOX_LTP_HTTP_FAILURE:", exc.code, flush=True)
        raise
    if payload.get("status") != "success" or not isinstance(payload.get("data"), dict):
        raise ValueError("UNEXPECTED_UPSTOX_RESPONSE")
    data = payload["data"]
    output = []
    for symbol, key in keys.items():
        quote = data.get(key.replace("|", ":")) or data.get(key) or next((v for v in data.values() if isinstance(v, dict) and v.get("instrument_token") == key), None)
        if not isinstance(quote, dict):
            continue
        price = quote.get("last_price")
        if not isinstance(price, (int, float)) or isinstance(price, bool) or not 0 < price < 10000000:
            continue
        # Upstox V3 last_trade_time is milliseconds; never use request time as trade time.
        timestamp = quote.get("last_trade_time")
        updated_at = None
        if timestamp is not None:
            try:
                from datetime import timezone
                updated_at = datetime.fromtimestamp(int(timestamp) / 1000, tz=timezone.utc).isoformat()
            except (ValueError, OverflowError, TypeError, OSError):
                pass
        output.append({"symbol": symbol, "price": price, "updated_at": updated_at})
    return output

def yahoo_daily_quotes():
    """Independent, best-effort Yahoo Finance daily historical closes; not live."""
    from datetime import timezone
    output = []
    for symbol in SYMBOLS:
        ticker = symbol.replace("&", "%26") + ".NS"
        url = "https://query1.finance.yahoo.com/v8/finance/chart/" + ticker + "?range=7d&interval=1d"
        request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0", "Accept": "application/json"})
        try:
            with urllib.request.urlopen(request, timeout=8) as response:
                data = json.load(response)
            result = data["chart"]["result"][0]
            timestamps = result.get("timestamp") or []
            closes = result["indicators"]["quote"][0]["close"]
            valid = [(ts, price) for ts, price in zip(timestamps, closes)
                     if isinstance(price, (int, float)) and not isinstance(price, bool) and 0 < price < 10000000]
            if not valid:
                continue
            ts, price = valid[-1]
            output.append({"symbol": symbol, "price": round(price, 2),
                           "updated_at": datetime.fromtimestamp(ts, tz=timezone.utc).isoformat(),
                           "source": "Yahoo Finance daily historical close", "quote_type": "DAILY_CLOSE_NOT_LIVE"})
        except (urllib.error.URLError, TimeoutError, ValueError, TypeError, KeyError, IndexError, OSError) as exc:
            print("YAHOO_DAILY_UNAVAILABLE:", symbol, type(exc).__name__, flush=True)
    return output


@lru_cache(maxsize=2)
def cached_breakouts(bucket):
    return analyze_watchlist(SYMBOLS)

class Handler(BaseHTTPRequestHandler):
    def do_HEAD(self):
        self.send_response(200 if self.path in ('/', '/long-term', '/health') else 404)
        self.send_header('Content-Length', '0')
        self.end_headers()

    def do_GET(self):
        if self.path == "/health":
            payload = {"status": "ok", "mode": "isolated-investment-preview",
                       "upstox_configured": bool(os.getenv("UPSTOX_ACCESS_TOKEN"))}
            return self.respond(200, payload)
        if self.path in ("/api/v2/watchlist-quotes", "/api/v2/watchlist-diagnostics"):
            upstox_error = None
            try:
                quotes = direct_upstox_quotes()
                for quote in quotes:
                    quote["source"] = "Upstox V3 LTP"
            except Exception as exc:
                upstox_error = exc.code if isinstance(exc, urllib.error.HTTPError) else type(exc).__name__
                print("WATCHLIST_UPSTOX_FAILURE:", type(exc).__name__, "http_status:", upstox_error, flush=True)
                quotes = []
            missing = set(SYMBOLS) - {q["symbol"] for q in quotes}
            if missing:
                quotes.extend(q for q in yahoo_daily_quotes() if q["symbol"] in missing)
            if self.path == "/api/v2/watchlist-diagnostics":
                return self.respond(200, {"requested": len(SYMBOLS), "valid": len(quotes),
                    "missing": [s for s in SYMBOLS if s not in {q["symbol"] for q in quotes}],
                    "upstox_error": upstox_error, "sources": sorted({q["source"] for q in quotes})})
            return self.respond(200, quotes)
        if self.path == "/api/v2/positional-breakouts":
            return self.respond(200, cached_breakouts(int(time.time() // 3600)))
        if self.path == "/api/v2/investment":
            now = datetime.now(ZoneInfo("Asia/Kolkata"))
            return self.respond(200, cached_snapshot(int(now.timestamp() // 900)))
        if self.path in ("/", "/long-term"):
            with open("v2/frontend/long-term.html", "rb") as f:
                page = f.read()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(page)))
            self.end_headers()
            self.wfile.write(page)
            return
        self.respond(404, {"error": "not found"})

    def respond(self, status, payload):
        data = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", "10000"))
    ThreadingHTTPServer(("0.0.0.0", port), Handler).serve_forever()
