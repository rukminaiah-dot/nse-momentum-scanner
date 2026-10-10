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
from functools import lru_cache
from v2.backend.investment_watchlist_57 import RESEARCH_UNIVERSE
from v2.backend.nse_daily_source import probe_latest
from v2.backend import nse_history_collector

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
    return [{"symbol": s, "status": "AWAITING_SCREENER_DATA", "entry": None, "stop": None, "target_2r": None, "target_3r": None} for s in RESEARCH_UNIVERSE]

class Handler(BaseHTTPRequestHandler):
    def do_HEAD(self):
        path = urllib.parse.urlsplit(self.path).path
        self.send_response(200 if path in ('/', '/long-term', '/health') else 404)
        self.send_header('Content-Length', '0')
        self.end_headers()

    def do_GET(self):
        self.path = urllib.parse.urlsplit(self.path).path
        if self.path == "/api/v2/nse-daily-closes":
            return self.respond(200, nse_history_collector.latest_closes())
        if self.path == "/api/v2/historical-data-status":
            return self.respond(200, nse_history_collector.snapshot())
        if self.path == "/api/v2/verified-positional-signals":
            return self.respond(200, nse_history_collector.signals())
        if self.path == "/api/v2/data-source-probe":
            return self.respond(200, probe_latest(days_back=3))
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
                pass  # Yahoo Finance disabled by user request
            if self.path == "/api/v2/watchlist-diagnostics":
                return self.respond(200, {"requested": len(SYMBOLS), "valid": len(quotes),
                    "missing": [s for s in SYMBOLS if s not in {q["symbol"] for q in quotes}],
                    "upstox_error": upstox_error, "sources": sorted({q["source"] for q in quotes})})
            return self.respond(200, quotes)
        if self.path == "/api/v2/research-watchlist":
            return self.respond(200, {"symbols": RESEARCH_UNIVERSE, "count": len(RESEARCH_UNIVERSE), "source": "user watchlist image plus earlier selections"})
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
    # One asynchronous startup probe: inspect Render outbound access without
    # blocking health checks or repeatedly downloading NSE files.
    import threading
    def startup_probe():
        try:
            result = probe_latest(days_back=3)
            print("NSE_SOURCE_PROBE_RESULT:", json.dumps(result), flush=True)
        except Exception as exc:
            print("NSE_SOURCE_PROBE_ERROR:", type(exc).__name__, flush=True)
    threading.Thread(target=startup_probe, daemon=True).start()
    import unittest
    from v2.backend import test_verified_positional_signals
    test_suite = unittest.defaultTestLoader.loadTestsFromModule(test_verified_positional_signals)
    test_result = unittest.TestResult()
    test_suite.run(test_result)
    print("POSITIONAL_TEST_RESULT:", json.dumps({"run":test_result.testsRun,
        "failures":len(test_result.failures), "errors":len(test_result.errors),
        "passed":test_result.wasSuccessful()}), flush=True)
    if test_result.wasSuccessful():
        nse_history_collector.start()
    else:
        print("NSE_HISTORY_BLOCKED_BY_FAILED_TESTS", flush=True)
    port = int(os.environ.get("PORT", "10000"))
    ThreadingHTTPServer(("0.0.0.0", port), Handler).serve_forever()
