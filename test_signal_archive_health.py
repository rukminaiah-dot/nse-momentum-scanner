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
            pg = Pg([("A", datetime(2026, 10, 14, 10), 100, "BUY"),
                     ("OLD", datetime(2026, 10, 13, 10), 90, "SELL")])
            result = compare_archive_keys(path, pg)
            self.assertEqual(result["status"], "MISSING_ARCHIVE_ROWS")
            self.assertEqual(result["missing_from_archive"], 1)
            self.assertEqual(result["missing_samples"][0]["symbol"], "A")
            self.assertEqual(result["extra_archive_observations"], 1)
            self.assertEqual(result["extra_archive_samples"][0]["symbol"], "OLD")
            self.assertIn("retained history", result["extra_archive_interpretation"])
            self.assertFalse(result["historical_completeness_verified"])
            self.assertFalse(result["available_source_reconciliation_verified"])
            self.assertEqual(result["verification_scope"], "CURRENT_SQLITE_ROWS_ONLY")
            pg.rows.append(("A", datetime(2026, 10, 14, 10, 1), 101, "SELL"))
            matched = compare_archive_keys(path, pg)
            self.assertEqual(matched["status"], "MATCHED_AVAILABLE_SOURCE")
            self.assertTrue(matched["available_source_reconciliation_verified"])
            self.assertFalse(matched["historical_completeness_verified"])
            self.assertEqual(matched["historical_audit_status"], "NOT_VERIFIABLE_FROM_CURRENT_SQLITE")

    def test_same_keys_with_different_signal_or_price_are_mismatched(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "signals.db"
            with sqlite3.connect(path) as con:
                con.execute("CREATE TABLE scanner_signal_history (symbol TEXT,candle_time TEXT,price REAL,signal TEXT)")
                con.executemany("INSERT INTO scanner_signal_history VALUES (?,?,?,?)", [
                    ("A", "2026-10-14 10:00:00", 100, "BUY"),
                    ("A", "2026-10-14 10:01:00", 101, "SELL"),
                ])
            pg = Pg([
                ("A", datetime(2026, 10, 14, 10), 100, "HOLD"),
                ("A", datetime(2026, 10, 14, 10, 1), 102, "SELL"),
            ])
            result = compare_archive_keys(path, pg)
            self.assertEqual(result["missing_from_archive"], 0)
            self.assertEqual(result["mismatched_archive_values"], 2)
            self.assertEqual(result["mismatched_samples"][0]["sqlite_signal"], "BUY")
            self.assertEqual(result["mismatched_samples"][0]["postgres_signal"], "HOLD")
            self.assertEqual(result["mismatched_samples"][1]["sqlite_price"], 101.0)
            self.assertEqual(result["mismatched_samples"][1]["postgres_price"], 102.0)
            self.assertEqual(result["status"], "MISMATCHED_ARCHIVE_VALUES")
            self.assertFalse(result["historical_completeness_verified"])

if __name__ == "__main__":
    unittest.main()
