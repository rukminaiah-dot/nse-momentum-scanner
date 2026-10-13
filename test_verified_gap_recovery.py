"""Offline regression tests for verified gap recovery (no Upstox credentials)."""
import unittest
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from v2.backend.verified_gap_recovery import validated_completed_rows, merge_verified_missing
from v2.backend.candle_manager import CandleManager

IST = ZoneInfo("Asia/Kolkata")
NOW = datetime(2026, 10, 13, 11, 45, tzinfo=IST)

def row(minute, volume=10):
    return [datetime(2026, 10, 13, 11, minute, tzinfo=IST).isoformat(),
            100, 103, 99, 102, volume]

class GapRecoveryTests(unittest.TestCase):
    def test_completed_only_and_order(self):
        got = validated_completed_rows([row(44), row(42), row(45)], NOW)
        self.assertEqual([t.minute for t in sorted(got)], [42, 44])

    def test_reject_bad_ohlcv(self):
        for bad in ([row(42, -1)], [row(42), row(42)],
                    [[row(42)[0], 100, 98, 99, 102, 10]],
                    [[row(42)[0], 100, 103, 99, float("nan"), 10]]):
            with self.subTest(bad=bad):
                with self.assertRaises(ValueError):
                    validated_completed_rows(bad, NOW)

    def test_reject_naive_current_clock(self):
        with self.assertRaises(ValueError):
            validated_completed_rows([row(42)], datetime(2026, 10, 13, 11, 45))

    def test_utc_current_clock_normalizes_to_ist(self):
        from datetime import timezone
        got = validated_completed_rows([row(42)], NOW.astimezone(timezone.utc))
        self.assertEqual([t.minute for t in got], [42])

    def test_reject_naive_timestamp(self):
        with self.assertRaises(ValueError):
            validated_completed_rows([["2026-10-13T11:42:00", 100, 103, 99, 102, 10]], NOW)

    def test_merge_only_missing_and_preserve_live(self):
        existing = validated_completed_rows([row(40), row(42)], NOW)
        recovered = validated_completed_rows([row(40, 500), row(41), row(42, 500), row(44)], NOW)
        merged, added = merge_verified_missing(
            [existing[t] for t in sorted(existing)], recovered,
            active_minute=datetime(2026, 10, 13, 11, 44))
        self.assertEqual([t.minute for t in added], [41])
        self.assertEqual([c.timestamp.minute for c in merged], [40, 41, 42])
        self.assertEqual(merged[0].volume, 10)

    def test_no_synthetic_missing_minutes(self):
        recovered = validated_completed_rows([row(40), row(43)], NOW)
        merged, added = merge_verified_missing([], recovered)
        self.assertEqual([t.minute for t in added], [40, 43])
        self.assertEqual(len(merged), 2)

    def test_prior_session_is_not_recovered(self):
        prior = ["2026-10-12T15:29:00+05:30", 100, 103, 99, 102, 10]
        got = validated_completed_rows([prior, row(42)], NOW)
        self.assertEqual([t.minute for t in got], [42])

    def test_history_limit(self):
        recovered = validated_completed_rows([row(i) for i in range(35, 45)], NOW)
        merged, added = merge_verified_missing([], recovered, limit=6)
        self.assertEqual(len(added), 6)
        self.assertEqual([t.minute for t in added], list(range(39, 45)))
        self.assertEqual([c.timestamp.minute for c in merged], list(range(39, 45)))

    def test_invalid_history_limit(self):
        with self.assertRaises(ValueError):
            merge_verified_missing([], {}, limit=0)

    def test_merge_rejected_after_active_minute_advances(self):
        manager = CandleManager()
        key = "TEST"
        def tick(minute):
            stamp = datetime(2026, 10, 13, 11, minute, tzinfo=IST)
            manager.update(key, 100, int(stamp.timestamp() * 1000), 10)
        tick(40)
        tick(42)
        _, expected_active = manager.recovery_snapshot(key)
        tick(43)
        recovered = validated_completed_rows([row(41)], NOW)
        self.assertEqual(manager.merge_recovered(key, recovered, expected_active), 0)
        self.assertEqual([c.timestamp.minute for c in manager.completed[key]], [40, 42])

    def test_merge_inserts_gap_without_overwriting_live(self):
        manager = CandleManager()
        key = "TEST"
        for minute in (40, 42):
            stamp = datetime(2026, 10, 13, 11, minute, tzinfo=IST)
            manager.update(key, 100, int(stamp.timestamp() * 1000), 10)
        _, expected_active = manager.recovery_snapshot(key)
        recovered = validated_completed_rows([row(40, 900), row(41)], NOW)
        self.assertEqual(manager.merge_recovered(key, recovered, expected_active), 1)
        self.assertEqual([c.timestamp.minute for c in manager.completed[key]], [40, 41])
        self.assertEqual(manager.completed[key][0].volume, 10)

if __name__ == "__main__":
    unittest.main()
