"""Offline API contract tests: paper P&L must remain hypothetical."""
import unittest
from unittest.mock import patch
from fastapi import HTTPException
from v2.backend import api

class PaperPnlApiTests(unittest.TestCase):
    def setUp(self):
        self.report = {"closed_calls": [{
            "symbol": "A", "kind": "stock", "buy_price": 100,
            "sell_price": 110, "buy_time_ist": "2026-10-14 10:00:00",
            "sell_time_ist": "2026-10-14 11:00:00"
        }]}
    def test_explicit_assumptions(self):
        with patch.object(api, "get_cumulative_signal_accuracy", return_value=self.report):
            result = api.get_signal_paper_pnl("2026-10-14", 10000, 1)
        self.assertEqual(result["net_stock_pnl_inr"], 900)
        self.assertEqual(result["mode"], "HYPOTHETICAL_STOCK_PAPER_MODEL")
        self.assertFalse(result["order_execution_enabled"])
    def test_invalid_cost_is_http_400(self):
        with patch.object(api, "get_cumulative_signal_accuracy", return_value=self.report):
            with self.assertRaises(HTTPException) as context:
                api.get_signal_paper_pnl("2026-10-14", 10000, -1)
        self.assertEqual(context.exception.status_code, 400)

if __name__ == "__main__":
    unittest.main()
