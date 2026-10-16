"""Offline trade ledger regression: HOLD cannot clear BUY or reopen CLOSED."""
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from v2.backend import trade_engine


class HoldPreservesActiveTradeTests(unittest.TestCase):
    def test_hold_keeps_buy_status_and_refreshes_price(self):
        with tempfile.TemporaryDirectory() as directory:
            db = Path(directory) / "trades.db"
            con = sqlite3.connect(db)
            con.execute("CREATE TABLE trades (id INTEGER PRIMARY KEY, status TEXT, current_price REAL, quote_observed_at_ist TEXT, quote_timestamp_verified INTEGER DEFAULT 0)")
            con.execute("CREATE TABLE trade_events (trade_id INTEGER, event_time TEXT, action TEXT, price REAL, reason TEXT)")
            con.execute("INSERT INTO trades (id, status, current_price) VALUES (1, 'BUY', 100)")
            con.execute("INSERT INTO trades (id, status, current_price) VALUES (2, 'CLOSED', 110)")
            con.commit()
            con.close()
            def connect():
                return sqlite3.connect(db)
            with patch.object(trade_engine, "connect", connect):
                trade_engine.update_state(1, 105, action="HOLD")
                trade_engine.update_state(2, 120, action="BUY")
            con = sqlite3.connect(db)
            self.assertEqual(con.execute("SELECT status, current_price FROM trades WHERE id=1").fetchone(), ("BUY", 105))
            self.assertEqual(con.execute("SELECT status, current_price FROM trades WHERE id=2").fetchone(), ("CLOSED", 110))
            self.assertEqual(con.execute("SELECT COUNT(*) FROM trade_events").fetchone()[0], 0)
            con.close()


if __name__ == "__main__":
    unittest.main()
