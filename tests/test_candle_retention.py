"""Offline tests for optional bounded candle history."""
import unittest
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from v2.backend.candle_manager import CandleManager
from v2.backend.candles import Candle


def bars(count):
    start = datetime(2026, 10, 16, 9, 15)
    result = []
    for i in range(count):
        c = Candle(100 + i, 0)
        c.timestamp = start + timedelta(minutes=i)
        result.append(c)
    return result


class RetentionTests(unittest.TestCase):
    def test_rejects_invalid_limits(self):
        for value in (0, -1, True, 1.5, "60"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                CandleManager(max_completed_per_symbol=value)

    def test_default_unbounded_and_preload_cap(self):
        full = CandleManager()
        full.preload_completed("X", bars(5))
        self.assertEqual(len(full.snapshot("X")[0]), 5)
        capped = CandleManager(max_completed_per_symbol=2)
        capped.preload_completed("X", bars(5))
        self.assertEqual([c.timestamp.minute for c in capped.snapshot("X")[0]], [18, 19])

    def test_live_rollover_caps_completed_not_active(self):
        manager = CandleManager(max_completed_per_symbol=2)
        start = datetime(2026, 10, 16, 9, 15, tzinfo=ZoneInfo("Asia/Kolkata"))
        for i in range(5):
            manager.update("X", 100 + i, int((start + timedelta(minutes=i)).timestamp() * 1000))
        completed, active = manager.snapshot("X")
        self.assertEqual([c.timestamp.minute for c in completed], [17, 18])
        self.assertEqual(active.minute, 19)

    def test_old_recovery_cannot_evict_recent_history(self):
        manager = CandleManager(max_completed_per_symbol=2)
        manager.preload_completed("X", bars(5)[3:])
        active_ts = datetime(2026, 10, 16, 9, 20, tzinfo=ZoneInfo("Asia/Kolkata"))
        manager.update("X", 105, int(active_ts.timestamp() * 1000))
        older = bars(1)[0]
        self.assertEqual(manager.insert_missing_completed("X", {older.timestamp: older}), 0)
        self.assertEqual([c.timestamp.minute for c in manager.snapshot("X")[0]], [18, 19])


if __name__ == "__main__":
    unittest.main()
