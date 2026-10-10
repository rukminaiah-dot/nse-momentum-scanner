"""Isolated, read-only preview service. Does not import the trading API."""
import json
import os
import urllib.request
import urllib.error
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from datetime import datetime
from zoneinfo import ZoneInfo
from v2.backend.investment import cached_snapshot

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
                with urllib.request.urlopen(request, timeout=10) as response:
                    rows = json.load(response)
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
                if self.path == "/api/v2/scanner-diagnostics":
                    return self.respond(200, {"upstream_rows": len(rows), "watchlist_rows": matched, "invalid_price_rows": invalid_price, "valid_watchlist_rows": len(selected)})
                return self.respond(200, selected if self.path == "/api/v2/scanner" else {"source": "existing scanner; not daily close", "quotes": selected})
            except (urllib.error.URLError, TimeoutError, ValueError, TypeError, OSError):
                return self.respond(503, {"error": "SCANNER_DATA_UNAVAILABLE", "quotes": []})
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
