import csv
import io
import unittest
from v2.backend.signal_daily_accuracy_csv import daily_accuracy_csv

class DailyAccuracyCsvTests(unittest.TestCase):
    def test_separates_stock_and_index_daily_accuracy(self):
        report = {"daily_by_sell_date": {
            "2026-10-14": {"stock_closed": 2, "stock_wins": 1, "stock_losses": 1,
                           "stock_flat": 0, "stock_points": 3.5,
                           "index_closed": 1, "index_wins": 0, "index_losses": 1,
                           "index_flat": 0, "index_points": -25.0}}}
        rows = list(csv.DictReader(io.StringIO(daily_accuracy_csv(report))))
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["stock_closed"], "2")
        self.assertEqual(rows[0]["stock_losses"], "1")
        self.assertEqual(rows[0]["index_losses"], "1")
        self.assertEqual(rows[0]["index_points_sum"], "-25.0")
        self.assertEqual(rows[0]["stock_price_difference_sum"], "3.5")
        self.assertEqual(rows[1]["sell_date_ist"], "TOTAL")
        self.assertEqual(rows[0]["archive_reconciliation_status"], "NOT_VERIFIED_FOR_THIS_REQUEST")
        self.assertEqual(rows[1]["archive_reconciliation_status"], "NOT_VERIFIED_FOR_THIS_REQUEST")
        self.assertEqual(rows[1]["stock_closed"], "2")
        self.assertEqual(rows[1]["index_points_sum"], "-25.0")
        self.assertEqual(rows[0]["stock_win_rate_pct"], "50.0")
        self.assertEqual(rows[0]["index_win_rate_pct"], "0.0")

    def test_total_sums_multiple_days_without_combining_index_and_stock(self):
        report = {"daily_by_sell_date": {
            "2026-10-13": {"stock_closed": 1, "stock_wins": 1, "stock_points": 2,
                           "index_closed": 1, "index_losses": 1, "index_points": -30},
            "2026-10-14": {"stock_closed": 2, "stock_losses": 2, "stock_points": -4,
                           "index_closed": 1, "index_wins": 1, "index_points": 50},
        }}
        rows = list(csv.DictReader(io.StringIO(daily_accuracy_csv(report))))
        self.assertEqual(rows[-1]["stock_closed"], "3")
        self.assertEqual(rows[-1]["stock_wins"], "1")
        self.assertEqual(rows[-1]["stock_losses"], "2")
        self.assertEqual(rows[-1]["index_closed"], "2")
        self.assertEqual(rows[-1]["stock_price_difference_sum"], "-2")
        self.assertEqual(rows[-1]["index_points_sum"], "20")
        self.assertEqual(rows[-1]["stock_win_rate_pct"], "33.33")
        self.assertEqual(rows[-1]["index_win_rate_pct"], "50.0")

    def test_no_closed_calls_has_blank_win_rate(self):
        rows = list(csv.DictReader(io.StringIO(daily_accuracy_csv({"daily_by_sell_date": {}}))))
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["sell_date_ist"], "TOTAL")
        self.assertEqual(rows[0]["stock_win_rate_pct"], "")
        self.assertEqual(rows[0]["index_win_rate_pct"], "")

if __name__ == "__main__":
    unittest.main()
