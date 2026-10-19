"""Persistent history summaries never infer missing learning labels."""

import unittest
from datetime import datetime, timezone

from v2.backend.persisted_learning import learning_report_from_records


class PersistedLearningTests(unittest.TestCase):
    def test_summarizes_verified_gross_outcomes_and_blocks_model_training(self):
        rows = [
            {
                "buy_time": datetime(2026, 10, 19, 9, 30, tzinfo=timezone.utc),
                "buy_price": 100,
                "sell_time": datetime(2026, 10, 19, 9, 35, tzinfo=timezone.utc),
                "sell_price": 102,
                "quantity": 2,
                "pnl_total": 4,
                "exit_reason": "TARGET_EXIT",
            },
            {
                "buy_time": datetime(2026, 10, 19, 9, 40, tzinfo=timezone.utc),
                "buy_price": 100,
                "sell_time": datetime(2026, 10, 19, 9, 45, tzinfo=timezone.utc),
                "sell_price": 99,
                "quantity": 1,
                "pnl_total": -1,
                "exit_reason": "STOP_LOSS",
            },
        ]

        report = learning_report_from_records(rows)

        self.assertEqual(report["source"], "daily_trade_history")
        self.assertEqual(report["closed_records_seen"], 2)
        self.assertEqual(report["complete_records"], 2)
        self.assertEqual(report["invalid_records_excluded"], 0)
        self.assertEqual(report["gross_loss_count"], 1)
        self.assertEqual(report["gross_loss_reasons"], {"STOP_LOSS": 1})
        self.assertEqual(report["gross_losses_by_nifty_recovery_state"], {"UNAVAILABLE": 1})
        self.assertEqual(report["model"]["status"], "BLOCKED_CONTEXT_AND_COST_LABELS_REQUIRED")
        self.assertFalse(report["recommendations_enabled"])
        self.assertFalse(report["broker_orders_enabled"])

    def test_excludes_bad_times_nonfinite_and_inconsistent_pnl(self):
        rows = [
            {
                "buy_time": datetime(2026, 10, 19, 9, 40, tzinfo=timezone.utc),
                "buy_price": 100,
                "sell_time": datetime(2026, 10, 19, 9, 35, tzinfo=timezone.utc),
                "sell_price": 99,
                "quantity": 1,
                "pnl_total": -1,
                "exit_reason": "STOP_LOSS",
            },
            {
                "buy_time": datetime(2026, 10, 19, 9, 30, tzinfo=timezone.utc),
                "buy_price": 100,
                "sell_time": datetime(2026, 10, 19, 9, 35, tzinfo=timezone.utc),
                "sell_price": 99,
                "quantity": 1,
                "pnl_total": float("nan"),
                "exit_reason": "STOP_LOSS",
            },
            {
                "buy_time": datetime(2026, 10, 19, 9, 30, tzinfo=timezone.utc),
                "buy_price": 100,
                "sell_time": datetime(2026, 10, 19, 9, 35, tzinfo=timezone.utc),
                "sell_price": 99,
                "quantity": 1,
                "pnl_total": -5,
                "exit_reason": "STOP_LOSS",
            },
        ]

        report = learning_report_from_records(rows)

        self.assertEqual(report["complete_records"], 0)
        self.assertEqual(report["invalid_records_excluded"], 3)
        self.assertEqual(report["gross_loss_count"], 0)
        self.assertEqual(report["model"]["status"], "INSUFFICIENT_VALID_HISTORY")

    def test_empty_ledger_stays_in_collection_mode_without_predictions(self):
        report = learning_report_from_records([])

        self.assertEqual(report["complete_records"], 0)
        self.assertEqual(report["model"]["status"], "COLLECTING_DATA")
        self.assertFalse(report["recommendations_enabled"])


if __name__ == "__main__":
    unittest.main()
