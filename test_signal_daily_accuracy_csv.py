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
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["stock_closed"], "2")
        self.assertEqual(rows[0]["stock_losses"], "1")
        self.assertEqual(rows[0]["index_losses"], "1")
        self.assertEqual(rows[0]["index_points_sum"], "-25.0")
        self.assertEqual(rows[0]["stock_price_difference_sum"], "3.5")

if __name__ == "__main__":
    unittest.main()
