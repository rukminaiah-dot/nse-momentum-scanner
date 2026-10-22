"""Offline CSV historical replay validation."""
import csv
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from v2.backend.experimental_15m_csv_backtest import read_bars, aggregate_results


class TestCsvReplay(unittest.TestCase):
    def test_aggregate_empty(self):
        from v2.backend.experimental_15m_backtest import TARGETS
        summary = aggregate_results([])
        self.assertEqual(set(summary), {str(t) for t in TARGETS})
        self.assertTrue(all(row["trades"] == 0 and row["win_rate_pct"] is None
                            for row in summary.values()))

    def test_aggregate_real_trade_results(self):
        from v2.backend.experimental_15m_backtest import TARGETS
        outcomes = {str(t): {"net_pct": 0.2} for t in TARGETS}
        outcomes2 = {str(t): {"net_pct": -0.1} for t in TARGETS}
        results = [{"trades": [{"outcomes": outcomes}, {"outcomes": outcomes2}]},
                   {"trades": []}]
        summary = aggregate_results(results)
        for row in summary.values():
            self.assertEqual(row["trades"], 2)
            self.assertEqual(row["symbols_with_trades"], 1)
            self.assertEqual(row["net_wins"], 1)
            self.assertEqual(row["win_rate_pct"], 50.0)
            self.assertAlmostEqual(row["average_net_pct"], 0.05)

    def test_timezone_conversion(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "bars.csv"
            with path.open("w", newline="") as file:
                writer = csv.writer(file)
                writer.writerow(["symbol", "timestamp", "open", "high", "low", "close", "volume"])
                writer.writerow(["TEST", "2026-10-21T03:45:00Z", 100, 102, 99, 101, 200])
            result = read_bars(path)
            self.assertEqual(result["TEST"][0]["timestamp"], datetime(2026, 10, 21, 9, 15))

    def test_duplicate_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "bars.csv"
            with path.open("w", newline="") as file:
                writer = csv.writer(file)
                writer.writerow(["symbol", "timestamp", "open", "high", "low", "close", "volume"])
                for _ in range(2):
                    writer.writerow(["TEST", "2026-10-21T09:15:00+05:30", 100, 102, 99, 101, 200])
            with self.assertRaises(ValueError):
                read_bars(path)


if __name__ == "__main__":
    unittest.main()
