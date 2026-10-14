import sqlite3
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from v2.backend.signal_archive_health import compare_archive_keys

class Pg:
    def __init__(self, rows):
        self.rows = rows
    def execute(self, sql):
        self.sql = sql
        return self
    def fetchall(self):
        return self.rows

class ArchiveHealthTests(unittest.TestCase):
    def test_missing_rows_detected_even_with_extra_archive_rows(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "signals.db"
            with sqlite3.connect(path) as con:
                con.execute("CREATE TABLE scanner_signal_history (symbol TEXT,candle_time TEXT,price REAL,signal TEXT)")
                con.executemany("INSERT INTO scanner_signal_history VALUES (?,?,?,?)", [
                    ("A", "2026-10-14 10:00:00", 100, "BUY"),
                    ("A", "2026-10-14 10:01:00", 101, "SELL"),
                ])
            pg = Pg([("A", datetime(2026, 10, 14, 10)),
                     ("OLD", datetime(2026, 10, 13, 10))])
            result = compare_archive_keys(path, pg)
            self.assertEqual(result["status"], "MISSING_ARCHIVE_ROWS")
            self.assertEqual(result["missing_from_archive"], 1)
            self.assertEqual(result["extra_archive_observations"], 1)
            self.assertFalse(result["historical_completeness_verified"])
            pg.rows.append(("A", datetime(2026, 10, 14, 10, 1)))
            self.assertEqual(compare_archive_keys(path, pg)["status"], "MATCHED_AVAILABLE_SOURCE")

if __name__ == "__main__":
    unittest.main()
