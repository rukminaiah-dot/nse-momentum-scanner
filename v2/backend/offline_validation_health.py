"""Minimal public health endpoint for isolated, credential-free offline CI staging.

Does not import the scanner, broker clients, database, or trading modules.
Does not serve files or disclose environment variables.
"""
from http.server import BaseHTTPRequestHandler, HTTPServer
import os


class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path != "/health":
            self.send_error(404)
            return
        payload = b'{"status":"ok","mode":"offline-validation"}\n'
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def do_HEAD(self):
        self.send_error(405)

    def log_message(self, fmt, *args):
        return


def main():
    if (os.environ.get("NSE_RECOVERY_MODE") != "disabled"
            or os.environ.get("NSE_ENABLE_VERIFIED_GAP_RECOVERY") != "0"):
        raise SystemExit("Offline staging requires explicitly disabled recovery")
    port = int(os.environ.get("PORT", "10000"))
    HTTPServer(("0.0.0.0", port), HealthHandler).serve_forever()


if __name__ == "__main__":
    main()
