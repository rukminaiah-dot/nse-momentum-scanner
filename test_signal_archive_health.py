import sqlite3
import tempfile
import unittest
from datetime import datetime, timezone
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
    def test_invalid_source_observation_cannot_verify_as_matched(self):
        invalid_rows = [
            (None, "2026-10-14 10:01:00", 101, "SELL"),
            ("B", None, 101, "SELL"),
            ("B", "not-a-timestamp", 101, "SELL"),
            ("B", "2026-10-14T10:01:00+05:30", 101, "SELL"),
            ("B", "2026-10-14 10:01:00", None, "SELL"),
            ("B", "2026-10-14 10:01:00", "bad", "SELL"),
        ]
        for bad_row in invalid_rows:
            with self.subTest(row=bad_row), tempfile.TemporaryDirectory() as folder:
                path = Path(folder) / "signals.db"
                with sqlite3.connect(path) as con:
                    con.execute("CREATE TABLE scanner_signal_history (symbol TEXT,candle_time TEXT,price REAL,signal TEXT)")
                    con.executemany("INSERT INTO scanner_signal_history VALUES (?,?,?,?)", [
                        ("A", "2026-10-14 10:00:00", 100, "BUY"), bad_row,
                    ])
                pg = Pg([("A", datetime(2026, 10, 14, 10), 100, "BUY")])
                with self.assertRaisesRegex(ValueError, "invalid SQLite"):
                    compare_archive_keys(path, pg)

    def test_nonpositive_and_nonfinite_source_prices_cannot_verify(self):
        for bad_price in (0, -1, float("inf"), float("-inf")):
            with self.subTest(price=bad_price), tempfile.TemporaryDirectory() as folder:
                path = Path(folder) / "signals.db"
                with sqlite3.connect(path) as con:
                    con.execute("CREATE TABLE scanner_signal_history (symbol TEXT,candle_time TEXT,price REAL,signal TEXT)")
                    con.executemany("INSERT INTO scanner_signal_history VALUES (?,?,?,?)", [
                        ("A", "2026-10-14 10:00:00", 100, "BUY"),
                        ("B", "2026-10-14 10:01:00", bad_price, "SELL"),
                    ])
                pg = Pg([("A", datetime(2026, 10, 14, 10), 100, "BUY")])
                with self.assertRaisesRegex(ValueError, "invalid SQLite signal price"):
                    compare_archive_keys(path, pg)

    def test_blank_source_symbol_cannot_verify(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "signals.db"
            with sqlite3.connect(path) as con:
                con.execute("CREATE TABLE scanner_signal_history (symbol TEXT,candle_time TEXT,price REAL,signal TEXT)")
                con.executemany("INSERT INTO scanner_signal_history VALUES (?,?,?,?)", [
                    ("A", "2026-10-14 10:00:00", 100, "BUY"),
                    ("   ", "2026-10-14 10:01:00", 101, "SELL"),
                ])
            with self.assertRaisesRegex(ValueError, "invalid SQLite signal candle key"):
                compare_archive_keys(path, Pg([("A", datetime(2026, 10, 14, 10), 100, "BUY")]))

    def test_equivalent_timestamp_formats_are_duplicate_source_keys(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "signals.db"
            with sqlite3.connect(path) as con:
                con.execute("CREATE TABLE scanner_signal_history (symbol TEXT,candle_time TEXT,price REAL,signal TEXT)")
                con.executemany("INSERT INTO scanner_signal_history VALUES (?,?,?,?)", [
                    ("A", "2026-10-14 10:00:00", 100, "BUY"),
                    ("A", "2026-10-14T10:00:00", 100, "BUY"),
                ])
            pg = Pg([("A", datetime(2026, 10, 14, 10), 100, "BUY")])
            result = compare_archive_keys(path, pg)
            self.assertEqual(result["status"], "DUPLICATE_SQLITE_OBSERVATIONS")
            self.assertEqual(result["duplicate_sqlite_candle_keys"], 1)
            self.assertEqual(result["sqlite_source_rows_scanned"], 2)
            self.assertEqual(result["sqlite_available_observations"], 1)
            self.assertFalse(result["available_source_reconciliation_verified"])
            with sqlite3.connect(path) as con:
                con.execute("UPDATE scanner_signal_history SET price=101 WHERE rowid=2")
            result = compare_archive_keys(path, pg)
            self.assertEqual(result["status"], "CONFLICTING_SQLITE_OBSERVATIONS")
            self.assertEqual(result["conflicting_sqlite_candle_keys"], 1)
            self.assertEqual(result["duplicate_sqlite_candle_keys"], 1)
            self.assertEqual(result["conflicting_sqlite_samples"], [
                {"symbol": "A", "candle_time_ist": "2026-10-14 10:00:00"}])
            self.assertFalse(result["available_source_reconciliation_verified"])

    def test_conflicting_sqlite_samples_are_bounded_and_sorted(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "signals.db"
            with sqlite3.connect(path) as con:
                con.execute("CREATE TABLE scanner_signal_history (symbol TEXT,candle_time TEXT,price REAL,signal TEXT)")
                rows = []
                for minute in reversed(range(12)):
                    stamp = f"2026-10-14 10:{minute:02d}:00"
                    rows.extend([("A", stamp, 100, "BUY"), ("A", stamp.replace(" ", "T"), 101, "SELL")])
                con.executemany("INSERT INTO scanner_signal_history VALUES (?,?,?,?)", rows)
            result = compare_archive_keys(path, Pg([]))
            self.assertEqual(result["status"], "CONFLICTING_SQLITE_OBSERVATIONS")
            self.assertEqual(result["conflicting_sqlite_candle_keys"], 12)
            self.assertEqual(result["duplicate_sqlite_candle_keys"], 12)
            self.assertEqual(len(result["conflicting_sqlite_samples"]), 10)
            self.assertEqual(result["conflicting_sqlite_samples"][0]["candle_time_ist"], "2026-10-14 10:00:00")
            self.assertEqual(result["conflicting_sqlite_samples"][-1]["candle_time_ist"], "2026-10-14 10:09:00")
            self.assertFalse(result["available_source_reconciliation_verified"])

    def test_duplicate_sqlite_samples_are_bounded_and_sorted(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "signals.db"
            with sqlite3.connect(path) as con:
                con.execute("CREATE TABLE scanner_signal_history (symbol TEXT,candle_time TEXT,price REAL,signal TEXT)")
                rows = []
                for minute in reversed(range(12)):
                    stamp = f"2026-10-14 10:{minute:02d}:00"
                    rows.extend([("A", stamp, 100, "BUY"), ("A", stamp.replace(" ", "T"), 100, "BUY")])
                con.executemany("INSERT INTO scanner_signal_history VALUES (?,?,?,?)", rows)
            result = compare_archive_keys(path, Pg([]))
            self.assertEqual(result["status"], "DUPLICATE_SQLITE_OBSERVATIONS")
            self.assertEqual(result["duplicate_sqlite_candle_keys"], 12)
            self.assertEqual(result["sqlite_source_rows_scanned"], 24)
            self.assertEqual(result["sqlite_available_observations"], 12)
            self.assertEqual(len(result["duplicate_sqlite_samples"]), 10)
            self.assertEqual(result["duplicate_sqlite_samples"][0]["candle_time_ist"], "2026-10-14 10:00:00")
            self.assertEqual(result["duplicate_sqlite_samples"][-1]["candle_time_ist"], "2026-10-14 10:09:00")
            self.assertFalse(result["available_source_reconciliation_verified"])

    def test_duplicate_archive_samples_are_bounded_and_sorted(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "signals.db"
            with sqlite3.connect(path) as con:
                con.execute("CREATE TABLE scanner_signal_history (symbol TEXT,candle_time TEXT,price REAL,signal TEXT)")
                con.execute("INSERT INTO scanner_signal_history VALUES (?,?,?,?)",
                            ("A", "2026-10-14 10:00:00", 100, "BUY"))
            rows = []
            for minute in reversed(range(12)):
                stamp = datetime(2026, 10, 14, 10, minute)
                rows.extend([("A", stamp, 100, "BUY"), ("A", stamp, 100, "BUY")])
            result = compare_archive_keys(path, Pg(rows))
            self.assertEqual(result["status"], "DUPLICATE_ARCHIVE_OBSERVATIONS")
            self.assertEqual(result["duplicate_archive_candle_keys"], 12)
            self.assertEqual(result["postgres_archive_rows_scanned"], 24)
            self.assertEqual(len(result["duplicate_archive_samples"]), 10)
            self.assertEqual(result["duplicate_archive_samples"][0]["candle_time_ist"], "2026-10-14 10:00:00")
            self.assertEqual(result["duplicate_archive_samples"][-1]["candle_time_ist"], "2026-10-14 10:09:00")
            self.assertFalse(result["available_source_reconciliation_verified"])

    def test_fractional_second_timestamp_format_matches_postgres_datetime(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "signals.db"
            with sqlite3.connect(path) as con:
                con.execute("CREATE TABLE scanner_signal_history (symbol TEXT,candle_time TEXT,price REAL,signal TEXT)")
                con.execute("INSERT INTO scanner_signal_history VALUES (?,?,?,?)",
                            ("A", "2026-10-14T10:00:00.123456", 100, "BUY"))
            pg = Pg([("A", datetime(2026, 10, 14, 10, 0, 0, 123456), 100, "BUY")])
            result = compare_archive_keys(path, pg)
            self.assertEqual(result["status"], "MATCHED_AVAILABLE_SOURCE")
            self.assertEqual(result["missing_from_archive"], 0)
            self.assertTrue(result["available_source_reconciliation_verified"])

    def test_fractional_second_mismatch_is_not_silently_matched(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "signals.db"
            with sqlite3.connect(path) as con:
                con.execute("CREATE TABLE scanner_signal_history (symbol TEXT,candle_time TEXT,price REAL,signal TEXT)")
                con.execute("INSERT INTO scanner_signal_history VALUES (?,?,?,?)",
                            ("A", "2026-10-14 10:00:00.123456", 100, "BUY"))
            pg = Pg([("A", datetime(2026, 10, 14, 10, 0, 0, 654321), 100, "BUY")])
            result = compare_archive_keys(path, pg)
            self.assertEqual(result["status"], "MISSING_ARCHIVE_ROWS")
            self.assertEqual(result["missing_from_archive"], 1)
            self.assertEqual(result["extra_archive_observations"], 1)
            self.assertFalse(result["available_source_reconciliation_verified"])

    def test_fractional_seconds_remain_distinct_archive_keys(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "signals.db"
            with sqlite3.connect(path) as con:
                con.execute("CREATE TABLE scanner_signal_history (symbol TEXT,candle_time TEXT,price REAL,signal TEXT)")
                con.executemany("INSERT INTO scanner_signal_history VALUES (?,?,?,?)", [
                    ("A", "2026-10-14 10:00:00.100000", 100, "BUY"),
                    ("A", "2026-10-14 10:00:00.200000", 101, "SELL"),
                ])
            pg = Pg([
                ("A", datetime(2026, 10, 14, 10, 0, 0, 100000), 100, "BUY"),
                ("A", datetime(2026, 10, 14, 10, 0, 0, 200000), 101, "SELL"),
            ])
            result = compare_archive_keys(path, pg)
            self.assertEqual(result["status"], "MATCHED_AVAILABLE_SOURCE")
            self.assertEqual(result["sqlite_available_observations"], 2)
            self.assertEqual(result["postgres_archive_observations"], 2)
            self.assertEqual(result["duplicate_sqlite_candle_keys"], 0)
            self.assertTrue(result["available_source_reconciliation_verified"])
            pg.rows.pop()
            result = compare_archive_keys(path, pg)
            self.assertEqual(result["status"], "MISSING_ARCHIVE_ROWS")
            self.assertEqual(result["missing_from_archive"], 1)
            self.assertFalse(result["available_source_reconciliation_verified"])

    def test_invalid_archive_rows_cannot_verify_as_matched(self):
        invalid_rows = [
            (None, datetime(2026, 10, 14, 10), 100, "BUY"),
            (" ", datetime(2026, 10, 14, 10), 100, "BUY"),
            ("A", None, 100, "BUY"),
            ("A", "2026-10-14 10:00:00", 100, "BUY"),
            ("A", datetime(2026, 10, 14, 10, tzinfo=timezone.utc), 100, "BUY"),
            ("A", datetime(2026, 10, 14, 10), 0, "BUY"),
            ("A", datetime(2026, 10, 14, 10), float("inf"), "BUY"),
            ("A", datetime(2026, 10, 14, 10), 100, "UNKNOWN"),
        ]
        for bad_row in invalid_rows:
            with self.subTest(row=bad_row), tempfile.TemporaryDirectory() as folder:
                path = Path(folder) / "signals.db"
                with sqlite3.connect(path) as con:
                    con.execute("CREATE TABLE scanner_signal_history (symbol TEXT,candle_time TEXT,price REAL,signal TEXT)")
                    con.execute("INSERT INTO scanner_signal_history VALUES (?,?,?,?)",
                                ("A", "2026-10-14 10:00:00", 100, "BUY"))
                with self.assertRaisesRegex(ValueError, "invalid PostgreSQL archive"):
                    compare_archive_keys(path, Pg([bad_row]))

    def test_duplicate_archive_rows_cannot_verify_as_matched(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "signals.db"
            with sqlite3.connect(path) as con:
                con.execute("CREATE TABLE scanner_signal_history (symbol TEXT,candle_time TEXT,price REAL,signal TEXT)")
                con.execute("INSERT INTO scanner_signal_history VALUES (?,?,?,?)",
                            ("A", "2026-10-14 10:00:00", 100, "BUY"))
            pg = Pg([
                ("A", datetime(2026, 10, 14, 10), 100, "BUY"),
                ("A", datetime(2026, 10, 14, 10), 101, "SELL"),
            ])
            result = compare_archive_keys(path, pg)
            self.assertEqual(result["status"], "DUPLICATE_ARCHIVE_OBSERVATIONS")
            self.assertEqual(result["duplicate_archive_candle_keys"], 1)
            self.assertEqual(result["postgres_archive_rows_scanned"], 2)
            self.assertEqual(result["postgres_archive_observations"], 1)
            self.assertEqual(result["duplicate_archive_samples"], [
                {"symbol": "A", "candle_time_ist": "2026-10-14 10:00:00"}])
            self.assertFalse(result["available_source_reconciliation_verified"])

    def test_duplicate_sqlite_keys_are_not_silently_accepted(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "signals.db"
            with sqlite3.connect(path) as con:
                con.execute("CREATE TABLE scanner_signal_history (symbol TEXT,candle_time TEXT,price REAL,signal TEXT)")
                con.executemany("INSERT INTO scanner_signal_history VALUES (?,?,?,?)", [
                    ("A", "2026-10-14 10:00:00", 100, "BUY"),
                    ("A", "2026-10-14 10:00:00", 100, "BUY"),
                ])
            pg = Pg([("A", datetime(2026, 10, 14, 10), 100, "BUY")])
            result = compare_archive_keys(path, pg)
            self.assertEqual(result["status"], "DUPLICATE_SQLITE_OBSERVATIONS")
            self.assertEqual(result["duplicate_sqlite_candle_keys"], 1)
            self.assertFalse(result["available_source_reconciliation_verified"])
            with sqlite3.connect(path) as con:
                con.execute("UPDATE scanner_signal_history SET price=101 WHERE rowid=2")
            result = compare_archive_keys(path, pg)
            self.assertEqual(result["status"], "CONFLICTING_SQLITE_OBSERVATIONS")
            self.assertEqual(result["conflicting_sqlite_candle_keys"], 1)
            self.assertFalse(result["available_source_reconciliation_verified"])

    def test_missing_sqlite_database_is_not_created_by_verification(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "not-present.db"
            with self.assertRaises(sqlite3.OperationalError):
                compare_archive_keys(path, Pg([]))
            self.assertFalse(path.exists())

    def test_missing_signal_history_table_is_an_error(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "signals.db"
            with sqlite3.connect(path) as con:
                con.execute("CREATE TABLE unrelated (id INTEGER)")
            with self.assertRaises(sqlite3.OperationalError):
                compare_archive_keys(path, Pg([]))

    def test_empty_sqlite_source_is_inconclusive_even_if_postgres_has_history(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "signals.db"
            with sqlite3.connect(path) as con:
                con.execute("CREATE TABLE scanner_signal_history (symbol TEXT,candle_time TEXT,price REAL,signal TEXT)")
            for archive_rows in ([], [("OLD", datetime(2026, 10, 13, 10), 90, "BUY")]):
                with self.subTest(archive_rows=archive_rows):
                    result = compare_archive_keys(path, Pg(archive_rows))
                    self.assertEqual(result["status"], "NO_AVAILABLE_SQLITE_OBSERVATIONS")
                    self.assertFalse(result["available_source_reconciliation_verified"])
                    self.assertFalse(result["historical_completeness_verified"])
                    self.assertEqual(result["sqlite_available_observations"], 0)

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
            self.assertEqual(result["mismatched_signal_values"], 1)
            self.assertEqual(result["mismatched_price_values"], 1)
            self.assertEqual(result["mismatched_samples"][0]["sqlite_signal"], "BUY")
            self.assertEqual(result["mismatched_samples"][0]["postgres_signal"], "HOLD")
            self.assertEqual(result["mismatched_samples"][1]["sqlite_price"], 101.0)
            self.assertEqual(result["mismatched_samples"][1]["postgres_price"], 102.0)
            self.assertEqual(result["status"], "MISMATCHED_ARCHIVE_VALUES")
            self.assertFalse(result["historical_completeness_verified"])

if __name__ == "__main__":
    unittest.main()
