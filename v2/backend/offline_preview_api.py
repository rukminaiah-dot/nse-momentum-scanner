"""Read-only API fixture for the V2 Preview; never accesses market data.

This service exposes the configured symbol universe and explicit empty states.
It does not import the scanner, broker SDK, database, or trading code.
"""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os

from .stock_universe import NIFTY_200

MODE = "OFFLINE_PREVIEW_NO_MARKET_DATA"


def _board():
    return [
        {
            "symbol": symbol,
            "data_status": "OFFLINE_PREVIEW",
            "last_price": None,
            "momentum_pct": None,
            "last_candle_ist": None,
        }
        for symbol in NIFTY_200
    ]


def response_for(path):
    if path == "/health":
        return {"status": "ok", "mode": MODE}
    if path == "/api/v2/preview-status":
        return {
            "mode": MODE,
            "market_data_connected": False,
            "historical_data_loaded": False,
            "order_execution_enabled": False,
            "source": "static_symbol_universe_only",
        }
    if path == "/api/v2/scanner":
        return []
    if path == "/api/v2/nifty200-stock-board":
        return {"stocks": _board(), "universe_size": len(NIFTY_200), "mode": MODE}
    if path == "/api/v2/quality-ratings":
        return {"ratings": [], "mode": MODE}
    if path == "/api/v2/nifty200-feed-health":
        return {
            "status": "OFFLINE_PREVIEW",
            "stocks_with_recent_ticks": 0,
            "universe_size": len(NIFTY_200),
            "market_data_connected": False,
            "order_execution_enabled": False,
        }
    if path == "/api/v2/decision-learning":
        return {
            "model": {"status": "OFFLINE_PREVIEW"},
            "complete_records": 0,
            "gross_loss_count": 0,
            "invalid_records_excluded": 0,
            "gross_loss_reasons": {},
            "gross_losses_by_nifty_recovery_state": {},
            "recommendations_enabled": False,
        }
    if path == "/api/v2/pnl-history":
        return {
            "status": "HISTORY_STORAGE_NOT_CONFIGURED",
            "source": "offline_preview",
            "days_requested": 7,
            "complete": False,
            "days": [],
            "order_execution_enabled": False,
        }
    if path == "/api/v2/signal-activity":
        return {
            "status": "HISTORY_STORAGE_NOT_CONFIGURED",
            "active": [],
            "completed": [],
            "source": "offline_preview",
            "order_execution_enabled": False,
        }
    if path == "/api/v2/trades":
        return []
    return None


class PreviewHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        payload = response_for(self.path)
        if payload is None:
            self.send_error(404)
            return
        body = json.dumps(payload, separators=(",", ":"), allow_nan=False).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        self.send_error(405)

    def do_PUT(self):
        self.send_error(405)

    def do_DELETE(self):
        self.send_error(405)

    def log_message(self, fmt, *args):
        return


def main():
    port = int(os.environ.get("PORT", "10000"))
    server = ThreadingHTTPServer(("0.0.0.0", port), PreviewHandler)
    server.daemon_threads = True
    server.serve_forever()


if __name__ == "__main__":
    main()
