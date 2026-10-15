"""Regression for bounded ordinary live candle rollover history (offline)."""
import unittest
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from v2.backend.candle_manager import CandleManager

IST = ZoneInfo("Asia/Kolkata")


class LiveRolloverRetentionTests(unittest.TestCase):
    def test_continuous_live_rollovers_keep_last_sixty(self):
        manager = CandleManager(log_closed_candles=False)
        start = datetime(2026, 10, 15, 9, 15, tzinfo=IST)
        for i in range(70):
            ts = int((start + timedelta(minutes=i)).timestamp() * 1000)
            manager.update("TEST", 100 + i, ts, 1)
        bars = manager.completed["TEST"]
        self.assertEqual(len(bars), 60)
        self.assertEqual(bars[0].timestamp, datetime(2026, 10, 15, 9, 24))
        self.assertEqual(bars[-1].timestamp, datetime(2026, 10, 15, 10, 23))
        self.assertEqual(manager.current["TEST"]["minute"],
                         datetime(2026, 10, 15, 10, 24))

    def test_verified_session_end_keeps_sixty_and_is_idempotent(self):
        manager = CandleManager(log_closed_candles=False)
        start = datetime(2026, 10, 15, 14, 20, tzinfo=IST)
        for i in range(70):
            ts = int((start + timedelta(minutes=i)).timestamp() * 1000)
            manager.update("TEST", 100 + i, ts, 1)
        self.assertEqual(len(manager.completed["TEST"]), 60)
        day = date(2026, 10, 15)
        schedule = {day: (time(9, 15), time(15, 30))}
        now = int(datetime(2026, 10, 15, 15, 30, tzinfo=IST).timestamp() * 1000)
        args = ("TEST", now, schedule, day, day, "Illustrative calendar", True)
        self.assertIsNotNone(manager.finalize_verified_session_end(*args))
        self.assertEqual(len(manager.completed["TEST"]), 60)
        self.assertEqual(manager.completed["TEST"][-1].timestamp,
                         datetime(2026, 10, 15, 15, 29))
        self.assertIsNone(manager.finalize_verified_session_end(*args))
        self.assertEqual(len(manager.completed["TEST"]), 60)

    def test_new_day_still_clears_prior_completed_bars(self):
        manager = CandleManager(log_closed_candles=False)
        first = int(datetime(2026, 10, 15, 15, 29, tzinfo=IST).timestamp() * 1000)
        next_day = int(datetime(2026, 10, 16, 9, 15, tzinfo=IST).timestamp() * 1000)
        manager.update("TEST", 100, first)
        manager.update("TEST", 101, next_day)
        self.assertNotIn("TEST", manager.completed)


if __name__ == "__main__":
    unittest.main()
