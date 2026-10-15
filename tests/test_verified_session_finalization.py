"""Offline-only verified-calendar finalization tests; no live feed or timers."""
import unittest
from datetime import date, datetime, time
from zoneinfo import ZoneInfo

from v2.backend.candle_manager import CandleManager

IST = ZoneInfo("Asia/Kolkata")
DAY = date(2026, 10, 15)
SCHEDULE = {DAY: (time(9, 15), time(15, 30))}


def ms(hour, minute):
    return int(datetime(2026, 10, 15, hour, minute, tzinfo=IST).timestamp() * 1000)


class VerifiedSessionFinalizationTests(unittest.TestCase):
    def setUp(self):
        self.manager = CandleManager(log_closed_candles=False)
        self.key = "TEST"
        self.manager.update(self.key, 100, ms(15, 29), 5)

    def finalize(self, hour, minute, schedule=SCHEDULE, verified=True, grace=5):
        return self.manager.finalize_verified_session_end(
            self.key, ms(hour, minute), schedule, DAY, DAY,
            "NSE circular reviewed", verified, grace)

    def test_finalizes_without_any_post_close_market_tick(self):
        closed = self.finalize(15, 30)
        self.assertIsNotNone(closed)
        self.assertEqual((closed.close, closed.volume), (100, 5))
        self.assertEqual(closed.timestamp, datetime(2026, 10, 15, 15, 29))
        self.assertNotIn(self.key, self.manager.current)
        self.assertEqual(len(self.manager.completed[self.key]), 1)
        self.assertIsNone(self.finalize(15, 31))
        self.assertEqual(len(self.manager.completed[self.key]), 1)

    def test_refuses_unverified_or_missing_calendar(self):
        self.assertIsNone(self.finalize(15, 30, verified=False))
        self.assertIsNone(self.finalize(15, 30, schedule={}))
        self.assertIn(self.key, self.manager.current)
        self.assertNotIn(self.key, self.manager.completed)

    def test_refuses_before_close_or_after_grace(self):
        self.assertIsNone(self.finalize(15, 29))
        self.assertIsNone(self.finalize(15, 36))
        self.assertIn(self.key, self.manager.current)

    def test_prior_day_candle_cannot_finalize_on_current_close(self):
        previous = datetime(2026, 10, 14, 15, 29)
        self.manager.current[self.key]["minute"] = previous
        self.assertIsNone(self.finalize(15, 30))
        self.assertEqual(self.manager.current[self.key]["minute"], previous)
        self.assertNotIn(self.key, self.manager.completed)

    def test_refuses_wrong_active_minute(self):
        self.manager.current[self.key]["minute"] = datetime(2026, 10, 15, 15, 28)
        self.assertIsNone(self.finalize(15, 30))
        self.assertIn(self.key, self.manager.current)


if __name__ == "__main__":
    unittest.main()
