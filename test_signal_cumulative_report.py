import unittest
from datetime import datetime
from v2.backend.signal_cumulative_report import cumulative_report, fetch_cumulative_archive

class FakeConnection:
    def __init__(self):
        self.params = None
    def execute(self, sql, params):
        self.params = params
        self.sql = sql
        return self
    def fetchall(self):
        return []

class CumulativeReportTests(unittest.TestCase):
    def test_overnight_trade_and_separate_index_points(self):
        rows = [
            ("A", "2026-10-13 15:20:00", 100, "BUY"),
            ("A", "2026-10-14 09:20:00", 110, "SELL"),
            ("NIFTY 50", "2026-10-14 09:25:00", 25000, "BUY"),
            ("NIFTY 50", "2026-10-14 09:30:00", 24950, "SELL"),
            ("A", "2026-10-14 09:20:00", 110, "SELL"),
        ]
        report = cumulative_report(rows, index_symbols={"NIFTY 50"})
        self.assertEqual(report["gross_closed_calls"], 2)
        self.assertEqual(report["stock"]["wins"], 1)
        self.assertEqual(report["index"]["losses"], 1)
        self.assertEqual(report["daily_by_sell_date"]["2026-10-14"]["stock_closed"], 1)
        self.assertEqual(report["daily_by_sell_date"]["2026-10-14"]["stock_wins"], 1)
        self.assertEqual(report["daily_by_sell_date"]["2026-10-14"]["index_losses"], 1)
        self.assertEqual(report["daily_by_sell_date"]["2026-10-14"]["stock_losses"], 0)
        self.assertIsNone(report["pnl_inr"])
        self.assertEqual(report["sell_readings"], 2)

    def test_repeated_buy_and_sell_readings_count_one_completed_call(self):
        rows = [
            ("A", "2026-10-14 09:15:00", 100, "BUY"),
            ("A", "2026-10-14 09:16:00", 101, "BUY"),
            ("A", "2026-10-14 09:17:00", 103, "BUY"),
            ("A", "2026-10-14 09:18:00", 105, "SELL"),
            ("A", "2026-10-14 09:19:00", 106, "SELL"),
            ("A", "2026-10-14 09:20:00", 107, "BUY"),
        ]
        report = cumulative_report(rows)
        self.assertEqual(report["buy_readings"], 4)
        self.assertEqual(report["sell_readings"], 2)
        self.assertEqual(report["gross_closed_calls"], 1)
        self.assertEqual(report["stock"]["wins"], 1)
        self.assertEqual(report["stock"]["open_calls"], 1)
        self.assertEqual(report["closed_calls"][0]["buy_price"], 100)
        self.assertEqual(report["closed_calls"][0]["sell_price"], 105)
        self.assertEqual(report["rejected_readings"], 3)
        self.assertEqual(report["duplicate_buy_readings"], 2)
        self.assertEqual(report["unmatched_sell_readings"], 1)
        self.assertEqual(report["gross_distinct_calls"], 2)
        self.assertEqual(report["gross_open_calls"], 1)

    def test_repeated_index_buy_does_not_create_extra_calls(self):
        rows = [
            ("NIFTY 50", "2026-10-14 09:15:00", 25000, "BUY"),
            ("NIFTY 50", "2026-10-14 09:16:00", 25010, "BUY"),
            ("NIFTY 50", "2026-10-14 09:17:00", 24990, "SELL"),
        ]
        report = cumulative_report(rows, index_symbols={"NIFTY 50"})
        self.assertEqual(report["gross_closed_calls"], 1)
        self.assertEqual(report["index"]["closed_calls"], 1)
        self.assertEqual(report["index"]["losses"], 1)
        self.assertEqual(report["index"]["net_points"], -10)
        self.assertEqual(report["rejected_readings"], 1)

    def test_archive_end_is_exclusive(self):
        connection = FakeConnection()
        fetch_cumulative_archive(connection, end_date="2026-10-14")
        self.assertEqual(connection.params, (datetime(2026, 10, 15),))

if __name__ == "__main__":
    unittest.main()
