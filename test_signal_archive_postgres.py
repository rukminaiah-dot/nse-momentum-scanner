import unittest
from datetime import datetime
from v2.backend.signal_archive_postgres import (
    DDL, archive_signal_rows, fetch_archive_day,
)

class FakeCursor:
    def __init__(self, row=None, rows=None):
        self.row = row
        self.rows = rows or []
    def fetchone(self):
        return self.row
    def fetchall(self):
        return self.rows

class FakeConnection:
    def __init__(self):
        self.seen = set()
        self.calls = []
    def execute(self, sql, params=None):
        self.calls.append((sql, params))
        if "INSERT INTO scanner_signal_archive" in sql:
            key = (params[0], params[1])
            if key in self.seen:
                return FakeCursor()
            self.seen.add(key)
            return FakeCursor(row=(params[0],))
        return FakeCursor(rows=[("NIFTY 50", datetime(2026, 10, 14, 10), 25000, "BUY")])

class SignalArchiveTests(unittest.TestCase):
    def test_schema_unique_candle_and_no_overwrite(self):
        self.assertIn("PRIMARY KEY (symbol, candle_time_ist)", DDL)
        con = FakeConnection()
        row = ("NIFTY 50", "2026-10-14 10:00:00", 25000, "BUY")
        self.assertEqual(archive_signal_rows(con, [row, row]), 1)
        self.assertEqual(archive_signal_rows(con, [row]), 0)
        self.assertIn("DO NOTHING", con.calls[0][0])

    def test_rejects_invalid_rows(self):
        for row in [
            ("A", "2026-10-14 10:00:00", -1, "BUY"),
            ("A", "2026-10-14 10:00:00", float("nan"), "BUY"),
            ("A", "2026-10-14 10:00:00", 10, "ORDER"),
            ("A", "2026-10-14T10:00:00+05:30", 10, "BUY"),
        ]:
            with self.subTest(row=row), self.assertRaises(ValueError):
                archive_signal_rows(FakeConnection(), [row])

    def test_daily_range_and_rows(self):
        con = FakeConnection()
        rows = fetch_archive_day(con, "2026-10-14")
        self.assertEqual(len(rows), 1)
        params = con.calls[0][1]
        self.assertEqual(params[0], datetime(2026, 10, 14))
        self.assertEqual(params[1], datetime(2026, 10, 15))

if __name__ == "__main__":
    unittest.main()
