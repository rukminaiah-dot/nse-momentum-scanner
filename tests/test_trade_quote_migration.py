"""Offline, isolated schema migration regression tests."""
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from v2.backend import database


class TradeQuoteMigrationTests(unittest.TestCase):
    def test_existing_trade_survives_additive_migration(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "ledger.db"
            con = sqlite3.connect(path)
            con.execute("CREATE TABLE trades (id INTEGER PRIMARY KEY, symbol TEXT, status TEXT)")
            con.execute("INSERT INTO trades VALUES (7, 'TEST', 'BUY')")
            con.commit()
            con.close()
            with patch.object(database, "DB_PATH", path):
                database.init_db()
                database.init_db()
            con = sqlite3.connect(path)
            self.assertEqual(con.execute("SELECT symbol, status, quote_observed_at_ist, quote_timestamp_verified FROM trades WHERE id=7").fetchone(),
                             ("TEST", "BUY", None, 0))
            con.close()


if __name__ == "__main__":
    unittest.main()
