"""Regression tests for volume-first paper research screening."""
import unittest
from datetime import datetime, timedelta
from v2.backend.experimental_15m_pipeline import screen_universe


class Test15mPaperPipeline(unittest.TestCase):
    def setUp(self):
        start = datetime(2026, 10, 21, 9, 15)
        self.bars = [{"timestamp": start + timedelta(minutes=15 * i),
                      "open": 100, "high": 102, "low": 99,
                      "close": 101, "volume": 180} for i in range(4)]
        self.now = self.bars[-1]["timestamp"] + timedelta(minutes=15)
        self.history = [{"timestamp": datetime(2026, 9, 1, 10, 0) + timedelta(days=i),
                         "volume": 100} for i in range(20)]

    def test_volume_gate_before_indicators(self):
        result = screen_universe({"A": self.bars}, {"A": self.history}, now=self.now)
        self.assertEqual(result["selected_count"], 1)
        self.assertEqual(result["selected"][0]["reason"], "INSUFFICIENT_15M_HISTORY")
        self.assertEqual(result["selected"][0]["relative_volume"], 1.8)

    def test_low_volume_excluded(self):
        bars = [dict(x) for x in self.bars]
        bars[-1]["volume"] = 120
        result = screen_universe({"A": bars}, {"A": self.history}, now=self.now)
        self.assertEqual(result["selected_count"], 0)
        self.assertEqual(result["excluded"]["A"], "VOLUME_BELOW_THRESHOLD")

    def test_nonfinite_volume_excluded(self):
        for value in (float("nan"), float("inf"), -1):
            with self.subTest(volume=value):
                bars = [dict(x) for x in self.bars]
                bars[-1]["volume"] = value
                result = screen_universe({"A": bars}, {"A": self.history}, now=self.now)
                self.assertEqual(result["selected_count"], 0)
                self.assertEqual(result["excluded"]["A"], "INVALID_CURRENT_VOLUME")

    def test_no_baseline_excluded(self):
        result = screen_universe({"A": self.bars}, {}, now=self.now)
        self.assertEqual(result["excluded"]["A"],
                         "MISSING_VERIFIED_20_SESSION_VOLUME_BASELINE")

    def test_rank_highest_volume_first(self):
        high = [dict(x) for x in self.bars]
        high[-1]["volume"] = 260
        result = screen_universe({"A": self.bars, "B": high},
                                 {"A": self.history, "B": self.history},
                                 now=self.now)
        self.assertEqual([x["symbol"] for x in result["selected"]], ["B", "A"])
        self.assertEqual(result["mode"], "PAPER")


if __name__ == "__main__":
    unittest.main()
