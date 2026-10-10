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
            try:
                quotes = direct_upstox_quotes()
                if self.path == "/api/v2/watchlist-diagnostics":
                    return self.respond(200, {"source": "upstox_v3_direct",
                                              "requested": len(SYMBOLS), "valid": len(quotes),
                                              "missing": [s for s in SYMBOLS if s not in {q["symbol"] for q in quotes}]})
                return self.respond(200, quotes)
            except Exception as exc:
                status = exc.code if isinstance(exc, urllib.error.HTTPError) else None
                print("WATCHLIST_UPSTOX_FAILURE:", type(exc).__name__, "http_status:", status, flush=True)
                return self.respond(503, {"error": "UPSTOX_QUOTES_UNAVAILABLE",
                                           "upstox_http_status": status, "quotes": []})
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
