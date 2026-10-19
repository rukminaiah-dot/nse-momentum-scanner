"""Isolated SQLite tests for the recorded BUY-to-SELL signal lifecycle."""
import sqlite3
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Barrier
from unittest.mock import patch

from v2.backend import trade_engine


def create_schema(path):
    with sqlite3.connect(path) as con:
        con.executescript("""
            CREATE TABLE trades (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol TEXT NOT NULL,
                signal_time TEXT NOT NULL,
                entry_price REAL NOT NULL,
                current_price REAL,
                target_1 REAL,
                target_2 REAL,
                invalidation REAL,
                status TEXT NOT NULL DEFAULT 'BUY',
                signal_reason TEXT,
                exit_reason TEXT,
                exit_time TEXT,
                exit_price REAL,
                realized_pnl REAL,
                realized_pnl_pct REAL
            );
            CREATE TABLE trade_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                trade_id INTEGER NOT NULL,
                event_time TEXT NOT NULL,
                action TEXT NOT NULL,
                price REAL,
                reason TEXT,
                FOREIGN KEY (trade_id) REFERENCES trades(id)
            );
            CREATE TABLE trade_decision_snapshots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                trade_id INTEGER NOT NULL,
                stage TEXT NOT NULL,
                event_time TEXT NOT NULL,
                context_json TEXT NOT NULL,
                FOREIGN KEY (trade_id) REFERENCES trades(id)
            );
        """)


class TradeEngineLifecycleTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tempdir.name) / "isolated-trades.sqlite"
        create_schema(self.db_path)
        self.db_patch = patch.object(trade_engine, "DB_PATH", self.db_path)
        self.db_patch.start()
        self.backup_patch = patch.object(trade_engine, "_backup_active_trade")
        self.backup_patch.start()
        self.sync_patch = patch.object(trade_engine, "_sync_completed_history")
        self.sync_patch.start()

    def tearDown(self):
        self.sync_patch.stop()
        self.backup_patch.stop()
        self.db_patch.stop()
        self.tempdir.cleanup()

    def test_buy_state_and_sell_are_persisted_once(self):
        context = {"features": {"rvol": 1.6}, "market_recovery": {
            "NIFTY 50": {"status": "POSSIBLE_REVERSAL", "recovery_fraction": 0.3}
        }}
        trade_id = trade_engine.buy("NSE_EQ|TEST", 100, 102, 104, 98, "test BUY", context=context)
        self.assertTrue(trade_engine.update_state(trade_id, 102, "TARGET_1", "target one", context=context))
        self.assertTrue(trade_engine.sell(trade_id, 103, "target two", context=context))

        # Repeated callbacks after closure cannot reopen or duplicate the exit.
        self.assertFalse(trade_engine.update_state(trade_id, 101, "BUY", "late update"))
        self.assertFalse(trade_engine.sell(trade_id, 101, "duplicate exit"))

        with sqlite3.connect(self.db_path) as con:
            row = con.execute("""
                SELECT status, entry_price, current_price, exit_price,
                       realized_pnl, realized_pnl_pct, exit_reason
                FROM trades WHERE id=?
            """, (trade_id,)).fetchone()
            events = con.execute(
                "SELECT action, price FROM trade_events WHERE trade_id=? ORDER BY id",
                (trade_id,),
            ).fetchall()
            snapshots = con.execute(
                "SELECT stage, context_json FROM trade_decision_snapshots WHERE trade_id=? ORDER BY id",
                (trade_id,),
            ).fetchall()

        self.assertEqual(row[:6], ("CLOSED", 100.0, 103.0, 103.0, 3.0, 3.0))
        self.assertEqual(row[6], "target two")
        self.assertEqual(events, [("BUY", 100.0), ("TARGET_1", 102.0), ("SELL", 103.0)])
        self.assertEqual([stage for stage, _ in snapshots], ["BUY", "TARGET_1", "SELL"])
        self.assertIn('"status":"POSSIBLE_REVERSAL"', snapshots[-1][1])
        self.assertEqual(trade_engine._backup_active_trade.call_args_list,
                         [unittest.mock.call(trade_id), unittest.mock.call(trade_id)])
        trade_engine._sync_completed_history.assert_called_once_with()

    def test_duplicate_buy_returns_one_active_lifecycle(self):
        first = trade_engine.buy("NSE_EQ|TEST", 100, 102, 104, 98, "first")
        second = trade_engine.buy("NSE_EQ|TEST", 101, 103, 105, 99, "repeat")
        self.assertEqual(first, second)
        with sqlite3.connect(self.db_path) as con:
            self.assertEqual(con.execute("SELECT COUNT(*) FROM trades").fetchone()[0], 1)
            self.assertEqual(con.execute("SELECT COUNT(*) FROM trade_events").fetchone()[0], 1)

    def test_concurrent_duplicate_buys_serialize_to_one_record(self):
        workers = 8
        barrier = Barrier(workers)

        def create_buy(_):
            barrier.wait(timeout=5)
            return trade_engine.buy("NSE_EQ|RACE", 100, 102, 104, 98, "parallel")

        with ThreadPoolExecutor(max_workers=workers) as executor:
            ids = list(executor.map(create_buy, range(workers)))

        self.assertEqual(len(set(ids)), 1)
        with sqlite3.connect(self.db_path) as con:
            self.assertEqual(con.execute("SELECT COUNT(*) FROM trades").fetchone()[0], 1)
            self.assertEqual(con.execute("SELECT COUNT(*) FROM trade_events").fetchone()[0], 1)

    def test_invalid_prices_fail_before_writing(self):
        for value in (0, -1, float("nan"), float("inf"), True, None):
            with self.subTest(value=value), self.assertRaises(ValueError):
                trade_engine.buy("NSE_EQ|BAD", value, 102, 104, 98, "invalid")
        with sqlite3.connect(self.db_path) as con:
            self.assertEqual(con.execute("SELECT COUNT(*) FROM trades").fetchone()[0], 0)

    def test_sell_rejects_terminal_state_changes_and_invalid_price(self):
        trade_id = trade_engine.buy("NSE_EQ|TEST", 100, 102, 104, 98, "test BUY")
        with self.assertRaises(ValueError):
            trade_engine.update_state(trade_id, 101, "CLOSED")
        with self.assertRaises(ValueError):
            trade_engine.sell(trade_id, float("nan"), "invalid exit")
        self.assertTrue(trade_engine.sell(trade_id, 99, "stop"))
        with sqlite3.connect(self.db_path) as con:
            self.assertEqual(con.execute("SELECT status FROM trades WHERE id=?", (trade_id,)).fetchone()[0], "CLOSED")
            self.assertEqual(con.execute("SELECT COUNT(*) FROM trade_events WHERE action='SELL'").fetchone()[0], 1)


if __name__ == "__main__":
    unittest.main()
