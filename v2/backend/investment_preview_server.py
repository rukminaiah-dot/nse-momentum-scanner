"""Isolated, read-only preview service. Does not import the trading API."""
import json
import os
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
