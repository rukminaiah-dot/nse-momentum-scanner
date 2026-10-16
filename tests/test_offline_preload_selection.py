"""Offline tests for scanner-equivalent completed intraday preload selection."""
import unittest
from datetime import datetime, timedelta
from v2.backend.candles import Candle
from v2.backend.offline_preload_selection import select_completed_preload


def bars(start, count):
    result = []
    for i in range(count):
        c = Candle(100 + i, 100)
        c.timestamp = start + timedelta(minutes=i)
        result.append(c)
    return result


class OfflinePreloadSelectionTests(unittest.TestCase):
    def setUp(self):
        self.start = datetime(2026, 10, 16, 9, 15)
        self.today = self.start.date()
        self.cutoff = self.start + timedelta(minutes=100)

    def select(self, historical, intraday, **kwargs):
        return select_completed_preload(
            historical, intraday, session_date=self.today,
            current_minute=self.cutoff, **kwargs)

    def test_latest_sixty_completed_candles_are_chronological(self):
        intraday = list(reversed(bars(self.start, 100)))
        selected = self.select([], intraday)
        self.assertEqual(len(selected), 60)
        self.assertEqual([c.timestamp for c in selected],
                         [c.timestamp for c in bars(self.start + timedelta(minutes=40), 60)])

    def test_current_forming_minute_and_future_are_excluded(self):
        intraday = bars(self.start, 102)
        selected = self.select([], intraday)
        self.assertEqual(selected[-1].timestamp,
                         self.cutoff - timedelta(minutes=1))

    def test_previous_session_and_duplicates_are_excluded(self):
        current = bars(self.start, 3)
        previous = bars(self.start - timedelta(days=1), 2)
        selected = self.select([], [previous[0], current[1], current[0],
                                    current[1], previous[1], current[2]])
        self.assertEqual([c.timestamp for c in selected],
                         [c.timestamp for c in current])

    def test_fallback_uses_historical_only_if_no_current_bars(self):
        historical = bars(self.start - timedelta(days=1), 90)
        self.assertEqual(self.select(historical, []), historical)
        self.assertEqual(self.select(historical, bars(self.cutoff, 2)), historical)
        self.assertEqual(self.select(historical, bars(self.start, 1)),
                         bars(self.start, 1))

    def test_invalid_limit_rejected(self):
        for limit in (0, -1, True, 1.5):
            with self.subTest(limit=limit):
                with self.assertRaises(ValueError):
                    self.select([], [], limit=limit)


if __name__ == "__main__":
    unittest.main()
