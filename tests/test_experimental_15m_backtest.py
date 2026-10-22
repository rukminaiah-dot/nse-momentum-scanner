"""Deterministic conservative paper scoring tests."""
import unittest
from v2.backend.experimental_15m_backtest import score_trade


class Test15mBacktest(unittest.TestCase):
    def test_target_after_cost(self):
        bars = [{"open": 100, "high": 101, "low": 99.9, "close": 100.5}]
        result = score_trade("PAPER_BUY", bars, cost_pct=0.1)
        self.assertEqual(result["0.5"]["outcome"], "TARGET")
        self.assertAlmostEqual(result["0.5"]["net_pct"], 0.4)

    def test_ambiguous_bar_assumes_stop(self):
        bars = [{"open": 100, "high": 101, "low": 99, "close": 100}]
        result = score_trade("PAPER_BUY", bars, cost_pct=0.1)
        self.assertEqual(result["0.3"]["outcome"], "STOP")

    def test_short_target(self):
        bars = [{"open": 100, "high": 100.1, "low": 99, "close": 99.4}]
        result = score_trade("PAPER_SELL", bars, cost_pct=0.1)
        self.assertEqual(result["0.5"]["outcome"], "TARGET")

    def test_no_order_mode(self):
        self.assertEqual(score_trade("WAIT", [], cost_pct=0.1), {})


if __name__ == "__main__":
    unittest.main()
