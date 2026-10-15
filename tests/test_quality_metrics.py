"""Tests for bounded observed-history metrics (no Upstox connection needed)."""
import unittest
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from v2.backend.quality_metrics import observed_history_gaps, summarize_observed_history


class ObservedHistoryGapTests(unittest.TestCase):
    def setUp(self):
        self.start = datetime(2026, 10, 15, 9, 15)
        self.today = self.start.date()

    def candles(self, offsets):
        return [SimpleNamespace(timestamp=self.start + timedelta(minutes=n))
                for n in offsets]

    def test_consecutive(self):
        self.assertEqual(observed_history_gaps(self.candles([0, 1, 2]), self.today),
                         {"observed_history_gap_minutes": 0,
                          "observed_history_candles_today": 3,
                          "observed_history_order_valid": True})

    def test_missing_minute(self):
        self.assertEqual(observed_history_gaps(self.candles([0, 2, 5]), self.today)
                         ["observed_history_gap_minutes"], 3)

    def test_duplicate_or_reordered_fails_closed(self):
        for offsets in ([0, 0, 1], [2, 1]):
            result = observed_history_gaps(self.candles(offsets), self.today)
            self.assertIsNone(result["observed_history_gap_minutes"])
            self.assertFalse(result["observed_history_order_valid"])

    def test_invalid_timestamp_fails_closed(self):
        invalid = [
            "2026-10-15T09:15:00",
            self.start.replace(tzinfo=timezone.utc),
            self.start.replace(second=30),
        ]
        for stamp in invalid:
            with self.subTest(stamp=stamp):
                result = observed_history_gaps(
                    [SimpleNamespace(timestamp=stamp)], self.today)
                self.assertIsNone(result["observed_history_gap_minutes"])
                self.assertFalse(result["observed_history_order_valid"])

    def test_summary_healthy_gapped_and_invalid(self):
        rows = {
            "HEALTHY": {"observed_history_gap_minutes": 0,
                        "observed_history_order_valid": True},
            "GAPPED": {"observed_history_gap_minutes": 3,
                       "observed_history_order_valid": True},
            "INVALID": {"observed_history_gap_minutes": None,
                        "observed_history_order_valid": False},
        }
        self.assertEqual(summarize_observed_history(rows), {
            "stocks_with_observed_history_gaps": 1,
            "observed_history_gap_minutes_total": 3,
            "stocks_with_unknown_observed_history": 1,
        })

    def test_summary_ignores_invalid_gap_values(self):
        rows = {
            "BOOLEAN": {"observed_history_gap_minutes": True},
            "NEGATIVE": {"observed_history_gap_minutes": -2},
            "MISSING": {},
        }
        self.assertEqual(summarize_observed_history(rows), {
            "stocks_with_observed_history_gaps": 0,
            "observed_history_gap_minutes_total": 0,
            "stocks_with_unknown_observed_history": 0,
        })

    def test_overnight_not_counted(self):
        yesterday = SimpleNamespace(timestamp=self.start - timedelta(days=1))
        result = observed_history_gaps([yesterday] + self.candles([0, 1]), self.today)
        self.assertEqual(result["observed_history_gap_minutes"], 0)
        self.assertEqual(result["observed_history_candles_today"], 2)

    def test_empty_history_is_not_full_session_proof(self):
        result = observed_history_gaps([], self.today)
        self.assertEqual(result["observed_history_candles_today"], 0)
        self.assertEqual(result["observed_history_gap_minutes"], 0)


if __name__ == "__main__":
    unittest.main()
