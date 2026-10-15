import sqlite3
import tempfile
import unittest
from pathlib import Path
from v2.backend.signal_archive_sync import sync_observed_signals

class FakeCursor:
    def __init__(self, row):
        self.row = row
    def fetchone(self):
        return self.row

class FakePg:
    def __init__(self):
        self.keys = set()
    def execute(self, sql, params):
        key = params[:2]
        if key in self.keys:
            return FakeCursor(None)
        self.keys.add(key)
        return FakeCursor((params[0],))

class SyncTests(unittest.TestCase):
    def test_bounded_sync_and_idempotent_replay(self):
        with tempfile.TemporaryDirectory() as folder:
            db = Path(folder) / "history.db"
            with sqlite3.connect(db) as con:
                con.execute("""CREATE TABLE scanner_signal_history
                    (symbol TEXT,candle_time TEXT,price REAL,signal TEXT)""")
                con.executemany("INSERT INTO scanner_signal_history VALUES (?,?,?,?)", [
                    ("A", "2026-10-14 10:00:00", 100, "BUY"),
                    ("A", "2026-10-14 10:01:00", 101, "HOLD"),
                    ("A", "2026-10-14 10:02:00", 102, "SELL"),
                    ("B", "2026-10-14 10:03:00", 200, "WAITING"),
                ])
            pg = FakePg()
            first = sync_observed_signals(db, pg, batch_size=2)
            second = sync_observed_signals(db, pg, batch_size=2)
            self.assertEqual((first["observations_scanned"], first["observations_inserted"]), (3, 3))
            self.assertEqual(second["observations_inserted"], 0)
            self.assertEqual(second["observations_already_present"], 3)
            self.assertFalse(second["existing_values_overwritten"])
            self.assertFalse(second["existing_value_matches_verified"])
            self.assertIn("verify", second["next_step"])

    def test_invalid_price_rejected_before_postgres_writes(self):
        for invalid_price in (None, 0, -10, "bad"):
            with self.subTest(price=invalid_price), tempfile.TemporaryDirectory() as folder:
                db = Path(folder) / "history.db"
                with sqlite3.connect(db) as con:
                    con.execute("CREATE TABLE scanner_signal_history (symbol TEXT,candle_time TEXT,price REAL,signal TEXT)")
                    con.executemany("INSERT INTO scanner_signal_history VALUES (?,?,?,?)", [
                        ("A", "2026-10-14 09:15:00", 100, "BUY"),
                        ("B", "2026-10-14 09:16:00", invalid_price, "SELL"),
                    ])
                pg = FakePg()
                with self.assertRaisesRegex(ValueError, "invalid SQLite signal price"):
                    sync_observed_signals(db, pg, batch_size=1)
                self.assertEqual(pg.keys, set())

    def test_duplicate_candle_rejected_before_postgres_writes(self):
        with tempfile.TemporaryDirectory() as folder:
            db = Path(folder) / "history.db"
            with sqlite3.connect(db) as con:
                con.execute("CREATE TABLE scanner_signal_history (symbol TEXT,candle_time TEXT,price REAL,signal TEXT)")
                con.executemany("INSERT INTO scanner_signal_history VALUES (?,?,?,?)", [
                    ("A", "2026-10-14 09:15:00", 100, "BUY"),
                    ("A", "2026-10-14 09:15:00", 101, "SELL"),
                ])
            pg = FakePg()
            with self.assertRaisesRegex(ValueError, "duplicate SQLite candle keys"):
                sync_observed_signals(db, pg, batch_size=1)
            self.assertEqual(pg.keys, set())

    def test_missing_source_database_is_not_created(self):
        with tempfile.TemporaryDirectory() as folder:
            db = Path(folder) / "missing.db"
            with self.assertRaises(sqlite3.OperationalError):
                sync_observed_signals(db, FakePg())
            self.assertFalse(db.exists())

    def test_missing_history_table_is_error(self):
        with tempfile.TemporaryDirectory() as folder:
            db = Path(folder) / "history.db"
            with sqlite3.connect(db) as con:
                con.execute("CREATE TABLE unrelated (id INTEGER)")
            with self.assertRaises(sqlite3.OperationalError):
                sync_observed_signals(db, FakePg())

    def test_invalid_batch_size(self):
        with self.assertRaises(ValueError):
            sync_observed_signals("unused", FakePg(), batch_size=0)

if __name__ == "__main__":
    unittest.main()
