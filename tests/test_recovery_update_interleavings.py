"""Deterministic offline recovery/update interleavings; no live scanner import."""
import unittest
from datetime import datetime, timedelta
from threading import Event, Thread
from zoneinfo import ZoneInfo

from v2.backend.candle_manager import CandleManager
from v2.backend.candles import Candle


IST = ZoneInfo("Asia/Kolkata")


def milliseconds(minute):
    return minute.replace(tzinfo=IST).timestamp() * 1000


def candle(minute, price=100):
    item = Candle(price, 10)
    item.timestamp = minute
    return item


class RecoveryUpdateInterleavingTests(unittest.TestCase):
    def setUp(self):
        self.start = datetime(2026, 10, 16, 9, 15)
        self.manager = CandleManager()
        self.manager.preload_completed(
            "SYM", [candle(self.start + timedelta(minutes=i))
                    for i in range(10) if i != 4])
        self.active = self.start + timedelta(minutes=10)
        self.manager.update("SYM", 100, milliseconds(self.active))

    def test_recovery_racing_with_rollover_never_overwrites_live_minute(self):
        captured = Event()
        resume = Event()
        outcome = []
        old_boundary = self.active
        missing = self.start + timedelta(minutes=4)

        def delayed_worker():
            captured.set()
            self.assertTrue(resume.wait(5), "test thread timed out")
            outcome.append(self.manager.merge_verified_recovery(
                "SYM", {missing: candle(missing)}, old_boundary))

        thread = Thread(target=delayed_worker)
        thread.start()
        try:
            self.assertTrue(captured.wait(5), "worker never captured snapshot")
            next_minute = self.active + timedelta(minutes=1)
            self.manager.update("SYM", 101, milliseconds(next_minute))
        finally:
            resume.set()
            thread.join(5)
        self.assertFalse(thread.is_alive())
        self.assertEqual(outcome, [1])
        completed, active = self.manager.snapshot("SYM")
        self.assertEqual(active, next_minute)
        self.assertEqual(len(completed), 11)
        self.assertEqual(len({c.timestamp for c in completed}), len(completed))

    def test_recovery_from_prior_session_cannot_merge_after_rollover(self):
        old_boundary = self.active
        missing = self.start + timedelta(minutes=4)
        tomorrow = self.active + timedelta(days=1)
        self.manager.update("SYM", 101, milliseconds(tomorrow))
        self.assertEqual(
            self.manager.merge_verified_recovery(
                "SYM", {missing: candle(missing)}, old_boundary), 0)
        completed, active = self.manager.snapshot("SYM")
        self.assertEqual(active, tomorrow)
        self.assertNotIn(missing, {c.timestamp for c in completed})

    def test_recovery_does_not_alias_mutable_caller_candles(self):
        missing = self.start + timedelta(minutes=4)
        recovered = candle(missing)
        self.assertEqual(self.manager.merge_verified_recovery(
            "SYM", {missing: recovered}, self.active), 1)
        recovered.close = -999
        completed, _ = self.manager.snapshot("SYM")
        self.assertNotEqual(next(c.close for c in completed
                                 if c.timestamp == missing), -999)


if __name__ == "__main__":
    unittest.main()
