"""Offline tests for market-recovery labeling and recorded-loss learning."""
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from v2.backend.decision_learning import (
    _train_logistic,
    classify_market_recovery,
    learning_report,
    serialize_context,
)
from v2.backend import database


class MarketRecoveryTests(unittest.TestCase):
    def test_three_hundred_points_is_an_example_not_a_fixed_threshold(self):
        nifty = classify_market_recovery(30000, 29700, 29790, 100)
        sensex = classify_market_recovery(40000, 39700, 39900, 100)
        self.assertEqual(nifty["large_move_threshold_points"], 300)
        self.assertEqual(nifty["status"], "POSSIBLE_REVERSAL")
        self.assertTrue(nifty["reversal_eligible"])
        self.assertEqual(sensex["large_move_threshold_points"], 400)
        self.assertEqual(sensex["status"], "NO_LARGE_MOVE")

    def test_atr_can_raise_the_large_move_threshold(self):
        result = classify_market_recovery(30000, 29700, 29900, 200)
        self.assertEqual(result["large_move_threshold_points"], 400)
        self.assertFalse(result["reversal_eligible"])
        self.assertEqual(result["status"], "NO_LARGE_MOVE")

    def test_reversal_states_require_large_move_and_confirmation_evidence(self):
        weak = classify_market_recovery(30000, 29700, 29730, 100)
        possible = classify_market_recovery(30000, 29700, 29790, 100)
        confirmed = classify_market_recovery(
            30000, 29700, 30000, 100, trend="BULLISH", above_vwap=True
        )
        failed = classify_market_recovery(
            30000, 29700, 29790, 100, prior_recovery_fraction=0.5
        )
        unconfirmed = classify_market_recovery(
            30000, 29700, 30000, 100, trend="BULLISH", above_vwap=None
        )
        self.assertEqual(weak["status"], "WEAKENING_SELLING")
        self.assertEqual(possible["status"], "POSSIBLE_REVERSAL")
        self.assertEqual(confirmed["status"], "CONFIRMED_LONG")
        self.assertEqual(failed["status"], "REVERSAL_FAILED")
        self.assertEqual(unconfirmed["status"], "POSSIBLE_REVERSAL")

    def test_invalid_or_contradictory_market_inputs_are_unavailable(self):
        result = classify_market_recovery(30000, 29800, 29700, 100)
        self.assertEqual(result, {"status": "UNAVAILABLE", "reversal_eligible": False})

    def test_context_rejects_non_finite_values(self):
        with self.assertRaises(ValueError):
            serialize_context({"features": {"rvol": float("nan")}})

    def test_model_waits_for_a_time_ordered_minimum_sample(self):
        self.assertEqual(_train_logistic([])["status"], "COLLECTING_DATA")

    def test_model_is_evaluated_on_later_records_and_against_a_baseline(self):
        # Deterministic algorithm fixture only; these are not market observations.
        start = datetime(2026, 1, 1, tzinfo=timezone.utc)
        rows = []
        for index in range(120):
            loss = index % 2 == 0
            rows.append({
                "signal_time": (start + timedelta(minutes=index)).isoformat(),
                "net_pnl": -1 if loss else 1,
                "entry_context": serialize_context({"features": {
                    "momentum_pct": -2 if loss else 2,
                    "price_vs_ema9_pct": -1 if loss else 1,
                }}),
            })
        report = _train_logistic(rows)
        self.assertEqual(report["status"], "SHADOW_VALIDATED")
        self.assertEqual(report["train_trades"], 96)
        self.assertEqual(report["validation_trades"], 24)
        self.assertLess(report["validation_brier"], report["baseline_brier"])
        self.assertFalse(report["recommendations_enabled"])

    def test_database_initialization_adds_snapshot_storage(self):
        with tempfile.TemporaryDirectory() as tempdir:
            test_db = Path(tempdir) / "test.sqlite"
            with patch.object(database, "DB_PATH", test_db):
                database.init_db()
            with sqlite3.connect(test_db) as con:
                tables = {row[0] for row in con.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                )}
                self.assertIn("trade_decision_snapshots", tables)
                columns = {row[1] for row in con.execute(
                    "PRAGMA table_info(trade_decision_snapshots)"
                )}
                self.assertTrue({"trade_id", "stage", "event_time", "context_json"} <= columns)


class LearningReportTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.path = Path(self.tempdir.name) / "learning.sqlite"
        with sqlite3.connect(self.path) as con:
            con.executescript("""
                CREATE TABLE trades (
                    id INTEGER PRIMARY KEY,
                    symbol TEXT,
                    signal_time TEXT,
                    entry_price REAL,
                    status TEXT,
                    exit_reason TEXT,
                    exit_time TEXT,
                    exit_price REAL,
                    realized_pnl REAL
                );
                CREATE TABLE trade_decision_snapshots (
                    id INTEGER PRIMARY KEY,
                    trade_id INTEGER,
                    stage TEXT,
                    event_time TEXT,
                    context_json TEXT
                );
            """)
            con.executemany("""
                INSERT INTO trades VALUES (?,?,?,?,?,?,?,?,?)
            """, [
                (1, "NIFTY_EQ|LOSS", "2026-10-15T09:30:00+05:30", 100,
                 "CLOSED", "Invalidation hit", "2026-10-15T10:00:00+05:30", 95, -5),
                (2, "NIFTY_EQ|WIN", "2026-10-15T09:30:00+05:30", 100,
                 "CLOSED", "Target 2 hit", "2026-10-15T10:00:00+05:30", 102, 2),
                (3, "NIFTY_EQ|BAD_TIME", "2026-10-15T11:00:00+05:30", 100,
                 "CLOSED", "Invalidation hit", "2026-10-15T10:00:00+05:30", 95, -5),
                (4, "NIFTY_EQ|BAD_PNL", "2026-10-15T09:30:00+05:30", 100,
                 "CLOSED", "Invalidation hit", "2026-10-15T10:00:00+05:30", 95, -4),
            ])
            entry = serialize_context({"features": {"rvol": 1.3}})
            exit_loss = serialize_context({"market_recovery": {
                "NIFTY 50": {"status": "POSSIBLE_REVERSAL"}
            }})
            con.executemany("INSERT INTO trade_decision_snapshots VALUES (?,?,?,?,?)", [
                (1, 1, "BUY", "2026-10-15T09:30:00+05:30", entry),
                (2, 1, "SELL", "2026-10-15T10:00:00+05:30", exit_loss),
                (3, 2, "BUY", "2026-10-15T09:30:00+05:30", entry),
                (4, 2, "SELL", "2026-10-15T10:00:00+05:30", "{}"),
            ])

    def tearDown(self):
        self.tempdir.cleanup()

    def test_report_excludes_invalid_history_and_tracks_loss_context(self):
        report = learning_report(self.path)
        self.assertEqual(report["closed_records_seen"], 4)
        self.assertEqual(report["complete_records"], 2)
        self.assertEqual(report["invalid_records_excluded"], 2)
        self.assertEqual(report["gross_loss_count"], 1)
        self.assertEqual(report["gross_loss_reasons"], {"Invalidation hit": 1})
        self.assertEqual(report["gross_losses_by_nifty_recovery_state"], {"POSSIBLE_REVERSAL": 1})
        self.assertEqual(report["model"]["status"], "BLOCKED_COST_ADJUSTED_LABELS_REQUIRED")
        self.assertFalse(report["recommendations_enabled"])
        self.assertFalse(report["broker_orders_enabled"])

    def test_missing_storage_does_not_infer_zero_losses(self):
        report = learning_report(self.path.parent / "missing.sqlite")
        self.assertEqual(report["status"], "NO_STORAGE")
        self.assertIsNone(report.get("gross_pnl"))
        self.assertEqual(report["gross_loss_count"], 0)


if __name__ == "__main__":
    unittest.main()
