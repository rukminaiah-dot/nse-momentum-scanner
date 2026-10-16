"""Offline tests for staging endpoint safety."""
import io
import json
import unittest
from unittest.mock import patch
from v2.backend import staging_health


class StagingHealthTests(unittest.TestCase):
    def test_refuses_start_without_offline_flag(self):
        with patch.dict("os.environ", {}, clear=True):
            with self.assertRaises(SystemExit):
                staging_health.main()

    def test_health_reports_no_feed_or_trading(self):
        handler = object.__new__(staging_health.Handler)
        handler.path = "/health"
        handler.wfile = io.BytesIO()
        statuses = []
        headers = {}
        handler.send_response = statuses.append
        handler.send_header = lambda key, value: headers.__setitem__(key, value)
        handler.end_headers = lambda: None
        handler.do_GET()
        self.assertEqual(statuses, [200])
        self.assertEqual(headers["Content-Type"], "application/json")
        self.assertEqual(json.loads(handler.wfile.getvalue()), {
            "status": "ready", "mode": "offline-staging",
            "upstox_connected": False, "trading_enabled": False,
        })

    def test_unknown_paths_are_not_served(self):
        handler = object.__new__(staging_health.Handler)
        handler.path = "/"
        failures = []
        handler.send_error = failures.append
        handler.do_GET()
        self.assertEqual(failures, [404])


if __name__ == "__main__":
    unittest.main()
