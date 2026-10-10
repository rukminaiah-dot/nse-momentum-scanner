"""Regression: restarting must not change the last verified quote timestamp."""
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from v2.backend import database


class ScannerRestartTimestampTest(unittest.TestCase):
    def test_reset_preserves_quote_timestamp_and_price(self):
        with tempfile.TemporaryDirectory() as directory:
            db = Path(directory) / "scanner.db"
            with patch.object(database, "DB_PATH", db):
                database.init_db()
                with sqlite3.connect(db) as con:
                    con.execute(
                        "UPDATE scanner_results SET updated_at=?, price=?, signal=? WHERE symbol=?",
                        ("2026-10-08 15:29:00", 123.45, "BUY", "POLYCAB"),
                    )
                database.reset_scanner_results()
                with sqlite3.connect(db) as con:
                    row = con.execute(
                        "SELECT updated_at, price, signal FROM scanner_results WHERE symbol=?",
                        ("POLYCAB",),
                    ).fetchone()
                self.assertEqual(row, ("2026-10-08 15:29:00", 123.45, "WAITING"))


if __name__ == "__main__":
    unittest.main()
