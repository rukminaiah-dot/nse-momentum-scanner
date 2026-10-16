import unittest
from v2.backend.signal_paper_pnl import model_stock_pnl

class PaperPnlTests(unittest.TestCase):
    def setUp(self):
        self.report = {"closed_calls": [
            {"symbol": "A", "kind": "stock", "buy_price": 100, "sell_price": 110,
             "buy_time_ist": "2026-10-14 10:00:00", "sell_time_ist": "2026-10-14 11:00:00"},
            {"symbol": "B", "kind": "stock", "buy_price": 200, "sell_price": 190,
             "buy_time_ist": "2026-10-14 10:00:00", "sell_time_ist": "2026-10-14 11:00:00"},
            {"symbol": "NIFTY 50", "kind": "index", "buy_price": 25000, "sell_price": 25100,
             "buy_time_ist": "2026-10-14 10:00:00", "sell_time_ist": "2026-10-14 11:00:00"},
        ]}
    def test_stock_only_costs_and_win_loss(self):
        result = model_stock_pnl(self.report, notional_inr=10000, round_trip_cost_pct=1)
        self.assertEqual(result["stock_closed_calls"], 2)
        self.assertEqual(result["index_calls_excluded"], 1)
        self.assertEqual(result["stock_wins_after_cost"], 1)
        self.assertEqual(result["stock_losses_after_cost"], 1)
        self.assertEqual(result["gross_stock_pnl_inr"], 500)
        self.assertEqual(result["net_stock_pnl_inr"], 300)
    def test_invalid_assumptions(self):
        for amount, cost in [(0, 0), (-1, 0), (10000, -1),
                             (10000, 101), (float("nan"), 0), (True, 0)]:
            with self.subTest(amount=amount, cost=cost), self.assertRaises(ValueError):
                model_stock_pnl(self.report, notional_inr=amount, round_trip_cost_pct=cost)

if __name__ == "__main__":
    unittest.main()
