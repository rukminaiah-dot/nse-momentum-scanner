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
    extra = nse_equity_keys() if missing else {}
    keys = {symbol: NIFTY_200.get(symbol) or extra.get(symbol) for symbol in SYMBOLS}
    if any(not key for key in keys.values()):
        raise LookupError("WATCHLIST_INSTRUMENT_KEY_MISSING")
    query = urllib.parse.urlencode({"instrument_key": ",".join(keys.values())})
    request = urllib.request.Request(
        "https://api.upstox.com/v3/market-quote/quotes?" + query,
        headers={"Accept": "application/json", "Authorization": "Bearer " + token})
    with urllib.request.urlopen(request, timeout=18) as response:
        payload = json.load(response)
    if payload.get("status") != "success" or not isinstance(payload.get("data"), dict):
        raise ValueError("UNEXPECTED_UPSTOX_RESPONSE")
    data = payload["data"]
    output = []
    for symbol, key in keys.items():
        quote = data.get(key.replace("|", ":"))
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
        if self.path in ("/api/v2/scanner-quotes", "/api/v2/scanner", "/api/v2/scanner-diagnostics"):
            # Read-only public scanner endpoint; never forwards the Upstox token.
            url = "https://nse-momentum-scanner-api.onrender.com/api/v2/scanner"
            try:
                request = urllib.request.Request(url, headers={"Accept": "application/json"})
                # Retry transient wake-up/deployment errors; never fabricate prices.
                rows = None
                for attempt in range(3):
                    try:
                        with urllib.request.urlopen(request, timeout=18) as response:
                            rows = json.load(response)
                        break
                    except urllib.error.HTTPError as exc:
                        if exc.code not in (502, 503, 504) or attempt == 2:
                            raise
                    except (urllib.error.URLError, TimeoutError):
                        if attempt == 2:
                            raise
                    time.sleep(1 + attempt)
                from v2.backend.investment import SYMBOLS, NIFTY_200
                by_key = {v: k for k, v in NIFTY_200.items()}
                selected = []
                matched = 0
                invalid_price = 0
                if not isinstance(rows, list):
                    raise ValueError("Unexpected scanner response")
                for row in rows:
                    if not isinstance(row, dict):
                        continue
                    symbol = row.get("symbol")
                    symbol = by_key.get(symbol, symbol)
                    if symbol not in SYMBOLS:
                        continue
                    matched += 1
                    price = row.get("price")
                    if not isinstance(price, (int, float)) or isinstance(price, bool) or not (0 < price < 10000000):
                        invalid_price += 1
                        continue
                    selected.append({"symbol": symbol, "price": price,
                                     "updated_at": row.get("updated_at") if isinstance(row.get("updated_at"), str) else None})
                # Scanner universe excludes COROMANDEL and DALBHARAT.
                # Supplement missing symbols from Upstox even when scanner responds 200.
                missing_symbols = set(SYMBOLS) - {item["symbol"] for item in selected}
                if missing_symbols:
                    try:
                        direct = direct_upstox_quotes()
                        selected.extend(item for item in direct if item["symbol"] in missing_symbols)
                    except Exception as exc:
                        status = exc.code if isinstance(exc, urllib.error.HTTPError) else None
                        print("UPSTOX_SUPPLEMENT_FAILURE:", type(exc).__name__,
                              "http_status:", status, flush=True)
                if self.path == "/api/v2/scanner-diagnostics":
                    return self.respond(200, {"upstream_rows": len(rows), "watchlist_rows": matched, "invalid_price_rows": invalid_price, "valid_watchlist_rows": len(selected)})
                return self.respond(200, selected if self.path == "/api/v2/scanner" else {"source": "existing scanner; not daily close", "quotes": selected})
            except (urllib.error.URLError, TimeoutError, ValueError, TypeError, OSError) as exc:
                # Log only the exception class and upstream HTTP status, never credentials.
                upstream_status = exc.code if isinstance(exc, urllib.error.HTTPError) else None
                print("SCANNER_UPSTREAM_FAILURE:", type(exc).__name__, "http_status:", upstream_status, flush=True)
                try:
                    selected = direct_upstox_quotes()
                    if self.path == "/api/v2/scanner-diagnostics":
                        return self.respond(200, {"source": "upstox_v3_direct", "upstream_rows": None,
                                                  "watchlist_rows": len(selected), "invalid_price_rows": 0,
                                                  "valid_watchlist_rows": len(selected)})
                    return self.respond(200, selected if self.path == "/api/v2/scanner" else
                                        {"source": "Upstox V3 direct quotes", "quotes": selected})
                except Exception as fallback_exc:
                    fallback_status = fallback_exc.code if isinstance(fallback_exc, urllib.error.HTTPError) else None
                    print("UPSTOX_DIRECT_FAILURE:", type(fallback_exc).__name__,
                          "http_status:", fallback_status, flush=True)
                    return self.respond(503, {"error": "QUOTE_SOURCES_UNAVAILABLE",
                                               "upstream_http_status": upstream_status,
                                               "upstox_http_status": fallback_status, "quotes": []})
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
