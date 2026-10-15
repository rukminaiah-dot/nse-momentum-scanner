"""Offline close-boundary tests: no broker, no live scanner, no orders."""
import unittest
from datetime import datetime
from zoneinfo import ZoneInfo

from v2.backend.candle_manager import CandleManager

IST = ZoneInfo("Asia/Kolkata")


def ms(hour, minute):
    return int(datetime(2026, 10, 15, hour, minute, tzinfo=IST).timestamp() * 1000)


class SessionFinalizationTests(unittest.TestCase):
    def test_last_minute_finalizes_once(self):
        manager = CandleManager(log_closed_candles=False)
        key = "TEST"
        self.assertIsNone(manager.update(key, 100, ms(15, 29), 5))
        self.assertIsNotNone(manager.finalize_last_regular_minute(key, ms(15, 30)))
        self.assertIsNone(manager.finalize_last_regular_minute(key, ms(15, 55)))
        self.assertEqual(len(manager.completed[key]), 1)
        self.assertEqual(manager.completed[key][0].timestamp,
                         datetime(2026, 10, 15, 15, 29))
        self.assertNotIn(key, manager.current)

    def test_gated_update_rejects_after_hours_without_new_bar(self):
        manager = CandleManager(log_closed_candles=False)
        key = "TEST"
        manager.update_regular_session(key, 100, ms(15, 29), 5)
        closed = manager.update_regular_session(key, 200, ms(15, 30), 999)
        self.assertIsNotNone(closed)
        self.assertEqual(closed.close, 100)
        self.assertEqual(closed.volume, 5)
        self.assertIsNone(manager.update_regular_session(key, 300, ms(15, 55), 999))
        self.assertNotIn(key, manager.current)
        self.assertEqual(len(manager.completed[key]), 1)

    def test_gated_update_never_starts_after_hours_bar(self):
        manager = CandleManager(log_closed_candles=False)
        self.assertIsNone(manager.update_regular_session(
            "TEST", 100, ms(15, 50), 5))
        self.assertNotIn("TEST", manager.current)

    def test_does_not_finalize_earlier_minute(self):
        manager = CandleManager(log_closed_candles=False)
        manager.update("TEST", 100, ms(15, 28), 5)
        self.assertIsNone(manager.finalize_last_regular_minute("TEST", ms(15, 30)))
        self.assertEqual(len(manager.completed.get("TEST", [])), 0)

    def test_does_not_finalize_during_session(self):
        manager = CandleManager(log_closed_candles=False)
        manager.update("TEST", 100, ms(15, 29), 5)
        self.assertIsNone(manager.finalize_last_regular_minute("TEST", ms(15, 29)))
        self.assertIn("TEST", manager.current)


if __name__ == "__main__":
    unittest.main()
