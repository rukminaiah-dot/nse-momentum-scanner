import csv
import io
import unittest
from v2.backend.signal_accuracy_csv import closed_calls_csv

class SignalAccuracyCsvTests(unittest.TestCase):
    def test_export_completed_calls_only(self):
        report = {"closed_calls": [
            {"symbol": "RELIANCE", "kind": "stock",
             "buy_time_ist": "2026-10-14 10:00:00",
             "sell_time_ist": "2026-10-14 10:05:00",
             "buy_price": 100, "sell_price": 110,
             "difference": 10, "return_pct": 10,
             "unrelated_field": "not exported"},
            {"symbol": "NIFTY 50", "kind": "index",
             "buy_time_ist": "2026-10-14 10:00:00",
             "sell_time_ist": "2026-10-14 10:05:00",
             "buy_price": 25000, "sell_price": 24900,
             "difference": -100, "return_pct": -0.4},
        ]}
        rows = list(csv.DictReader(io.StringIO(closed_calls_csv(report))))
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["symbol"], "RELIANCE")
        self.assertEqual(rows[1]["kind"], "index")
        self.assertEqual(rows[1]["difference"], "-100")
        self.assertNotIn("unrelated_field", rows[0])

    def test_empty_report_keeps_header(self):
        self.assertEqual(len(closed_calls_csv({"closed_calls": []}).splitlines()), 1)

if __name__ == "__main__":
    unittest.main()
