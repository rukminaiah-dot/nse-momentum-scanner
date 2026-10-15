"""Regression for bounded ordinary live candle rollover history (offline)."""
import unittest
from datetime import datetime, timedelta
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

    def test_new_day_still_clears_prior_completed_bars(self):
        manager = CandleManager(log_closed_candles=False)
        first = int(datetime(2026, 10, 15, 15, 29, tzinfo=IST).timestamp() * 1000)
        next_day = int(datetime(2026, 10, 16, 9, 15, tzinfo=IST).timestamp() * 1000)
        manager.update("TEST", 100, first)
        manager.update("TEST", 101, next_day)
        self.assertNotIn("TEST", manager.completed)


if __name__ == "__main__":
    unittest.main()
