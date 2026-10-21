"""Offline CSV historical replay validation."""
import csv
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from v2.backend.experimental_15m_csv_backtest import read_bars


class TestCsvReplay(unittest.TestCase):
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
