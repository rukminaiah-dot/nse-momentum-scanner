import unittest
from v2.backend.signal_accuracy_report import report_from_rows

class DailySignalAccuracyTests(unittest.TestCase):
    def test_stock_and_index_are_separate(self):
        rows = [
            ("RELIANCE", "2026-10-14 10:00:00", 100, "BUY"),
            ("RELIANCE", "2026-10-14 10:01:00", 102, "BUY"),
            ("RELIANCE", "2026-10-14 10:02:00", 110, "SELL"),
            ("NIFTY 50", "2026-10-14 10:00:00", 25000, "BUY"),
            ("NIFTY 50", "2026-10-14 10:03:00", 24900, "SELL"),
            ("RELIANCE", "2026-10-14 10:04:00", 115, "SELL"),
            ("RELIANCE", "2026-10-15 10:00:00", 130, "BUY"),
        ]
        r = report_from_rows(rows, day="2026-10-14", index_symbols={"NIFTY 50"})
        self.assertEqual(r["gross_buy_readings"], 3)
        self.assertEqual(r["gross_sell_readings"], 3)
        self.assertEqual(r["stock"]["wins"], 1)
        self.assertEqual(r["index"]["losses"], 1)
        self.assertEqual(r["rejected_readings"], 2)
        self.assertEqual(len(r["closed_calls"]), 2)
        self.assertEqual(r["stock"]["net_points"], 10)
        self.assertEqual(r["index"]["net_points"], -100)

    def test_no_history_is_not_a_perfect_score(self):
        r = report_from_rows([], day="2026-10-14")
        self.assertEqual(r["status"], "NO_RECORDED_SIGNALS")
        self.assertIsNone(r["stock"]["win_rate_pct"])

if __name__ == "__main__":
    unittest.main()
