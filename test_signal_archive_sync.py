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

    def test_invalid_batch_size(self):
        with self.assertRaises(ValueError):
            sync_observed_signals("unused", FakePg(), batch_size=0)

if __name__ == "__main__":
    unittest.main()
