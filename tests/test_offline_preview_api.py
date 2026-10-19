import json
import threading
import unittest
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer

from v2.backend.offline_preview_api import MODE, PreviewHandler
from v2.backend.stock_universe import NIFTY_200


class OfflinePreviewApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), PreviewHandler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.port = cls.server.server_address[1]

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=2)

    def request(self, method, path):
        connection = HTTPConnection("127.0.0.1", self.port, timeout=2)
        connection.request(method, path)
        response = connection.getresponse()
        body = response.read()
        connection.close()
        content_type = response.getheader("Content-Type") or ""
        payload = json.loads(body) if body and "application/json" in content_type else None
        return response.status, content_type, payload

    def test_preview_status_explicitly_disables_data_and_orders(self):
        status, content_type, payload = self.request("GET", "/api/v2/preview-status")
        self.assertEqual(status, 200)
        self.assertIn("application/json", content_type)
        self.assertEqual(payload["mode"], MODE)
        self.assertFalse(payload["market_data_connected"])
        self.assertFalse(payload["historical_data_loaded"])
        self.assertFalse(payload["order_execution_enabled"])

    def test_board_lists_symbols_without_prices_or_scores(self):
        status, _, payload = self.request("GET", "/api/v2/nifty200-stock-board")
        self.assertEqual(status, 200)
        self.assertEqual(payload["universe_size"], 200)
        self.assertEqual({row["symbol"] for row in payload["stocks"]}, set(NIFTY_200))
        self.assertTrue(all(row["last_price"] is None for row in payload["stocks"]))
        self.assertTrue(all(row["momentum_pct"] is None for row in payload["stocks"]))
        self.assertTrue(all(row["data_status"] == "OFFLINE_PREVIEW" for row in payload["stocks"]))

    def test_signals_trades_and_history_are_empty(self):
        for path in ("/api/v2/scanner", "/api/v2/trades"):
            status, _, payload = self.request("GET", path)
            self.assertEqual(status, 200)
            self.assertEqual(payload, [])
        status, _, payload = self.request("GET", "/api/v2/quality-ratings")
        self.assertEqual(status, 200)
        self.assertEqual(payload["ratings"], [])
        status, _, payload = self.request("GET", "/api/v2/signal-activity")
        self.assertEqual(status, 200)
        self.assertEqual(payload["active"], [])
        self.assertEqual(payload["completed"], [])
        self.assertFalse(payload["order_execution_enabled"])

    def test_unknown_routes_return_404_and_writes_are_rejected(self):
        self.assertEqual(self.request("GET", "/api/v2/not-a-route")[0], 404)
        self.assertEqual(self.request("POST", "/api/v2/scanner")[0], 405)
        self.assertEqual(self.request("PUT", "/api/v2/trades")[0], 405)
        self.assertEqual(self.request("DELETE", "/api/v2/trades")[0], 405)


if __name__ == "__main__":
    unittest.main()
