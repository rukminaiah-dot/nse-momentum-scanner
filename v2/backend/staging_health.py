"""Nonproduction health-only HTTP endpoint; does not start scanner or broker."""
import json
import os
from http.server import BaseHTTPRequestHandler, HTTPServer


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path != "/health":
            self.send_error(404)
            return
        body = json.dumps({"status": "ready", "mode": "offline-staging",
                           "upstox_connected": False,
                           "trading_enabled": False}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format, *args):
        # No request paths, credentials, or client identifiers in logs.
        pass


def main():
    if os.getenv("STAGING_OFFLINE_ONLY") != "1":
        raise SystemExit("Refusing to start without STAGING_OFFLINE_ONLY=1")
    HTTPServer(("0.0.0.0", int(os.environ.get("PORT", "10000"))),
               Handler).serve_forever()


if __name__ == "__main__":
    main()
