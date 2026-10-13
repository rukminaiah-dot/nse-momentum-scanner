"""Integration gate tests: live candle closure must precede a recovery request."""
import unittest
from datetime import datetime
from types import SimpleNamespace
from v2.backend.recovery_trigger import should_request_recovery
from v2.backend.candle_manager import CandleManager
from v2.backend.verified_gap_recovery import validated_completed_rows

def minute(day, n):
    return datetime(2026, 10, day, 11, n)

def history(*times):
    return [SimpleNamespace(timestamp=t) for t in times]

class RecoveryTriggerTests(unittest.TestCase):
    def gate(self, h, active, **overrides):
        opts = dict(enabled=True, stock=True, candle_closed=True)
        opts.update(overrides)
        return should_request_recovery(h, active, **opts)

    def test_observed_same_day_gap_triggers(self):
        self.assertTrue(self.gate(history(minute(13, 40), minute(13, 42)), minute(13, 43)))

    def test_contiguous_minutes_do_not_trigger(self):
        self.assertFalse(self.gate(history(minute(13, 40), minute(13, 41)), minute(13, 42)))

    def test_trailing_gap_with_single_closed_candle(self):
        self.assertTrue(self.gate(history(minute(13, 40)), minute(13, 43)))
        self.assertFalse(self.gate(history(minute(13, 42)), minute(13, 43)))

    def test_disabled_index_and_nonclosure_fail_closed(self):
        h = history(minute(13, 40), minute(13, 42))
        for flag in ("enabled", "stock", "candle_closed"):
            with self.subTest(flag=flag):
                self.assertFalse(self.gate(h, minute(13, 43), **{flag: False}))

    def test_overnight_and_stale_gap_fail_closed(self):
        self.assertFalse(self.gate(history(minute(12, 40), minute(13, 42)), minute(13, 43)))
        self.assertFalse(self.gate(history(minute(13, 40), minute(13, 42)), minute(13, 42)))
        self.assertFalse(self.gate(history(minute(13, 40), minute(13, 42)), minute(14, 43)))

    def test_live_closure_recovery_and_followup_continuity(self):
        from zoneinfo import ZoneInfo
        manager = CandleManager()
        key = "STOCK"
        ist = ZoneInfo("Asia/Kolkata")
        def tick(m):
            stamp = datetime(2026, 10, 13, 11, m, tzinfo=ist)
            return manager.update(key, 100, int(stamp.timestamp() * 1000), 10)
        self.assertIsNone(tick(40))
        self.assertIsNotNone(tick(42))
        history, active = manager.recovery_snapshot(key)
        self.assertTrue(self.gate(history, active))
        self.assertIsNotNone(tick(43))
        history, active = manager.recovery_snapshot(key)
        self.assertTrue(self.gate(history, active))
        rows = [["2026-10-13T11:41:00+05:30", 100, 102, 99, 101, 12]]
        recovered = validated_completed_rows(rows, datetime(2026, 10, 13, 11, 44, tzinfo=ist))
        self.assertEqual(manager.merge_recovered(key, recovered, active), 1)
        history, active = manager.recovery_snapshot(key)
        self.assertEqual([c.timestamp.minute for c in history], [40, 41, 42])
        self.assertFalse(self.gate(history, active))
        self.assertIsNotNone(tick(44))
        history, active = manager.recovery_snapshot(key)
        self.assertEqual([c.timestamp.minute for c in history], [40, 41, 42, 43])
        self.assertFalse(self.gate(history, active))

    def test_incomplete_history_fails_closed(self):
        self.assertFalse(self.gate([], minute(13, 43)))
        self.assertTrue(self.gate(history(minute(13, 40)), minute(13, 43)))
        self.assertFalse(self.gate(history(minute(13, 40), None), minute(13, 43)))

if __name__ == "__main__":
    unittest.main()
