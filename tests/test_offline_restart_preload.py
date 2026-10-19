"""Offline restart/preload replay: real scanner selection rule, no scanner import.

Checks that a restart preloads the full completed current session and preserves
indicator and decision continuity against uninterrupted processing.
"""
import unittest
from datetime import datetime, timedelta

from v2.backend.candles import Candle
from v2.backend.offline_preload_selection import select_completed_preload
from v2.backend.offline_signal_parity import evaluate


def session(start, prices):
    candles = []
    for i, price in enumerate(prices):
        candle = Candle(price, 100)
        candle.timestamp = start + timedelta(minutes=i)
        candles.append(candle)
    return candles


class ScannerRestartPreloadTests(unittest.TestCase):
    def setUp(self):
        self.start = datetime(2026, 10, 16, 9, 15)
        self.day = self.start.date()

    def test_restart_preload_keeps_full_completed_session(self):
        full = session(self.start, [100 + i * 0.03 for i in range(300)])
        cutoff = self.start + timedelta(minutes=300)
        selected = select_completed_preload([], list(reversed(full)),
                                            session_date=self.day,
                                            current_minute=cutoff)
        self.assertEqual(len(selected), 300)
        self.assertEqual([c.timestamp for c in selected],
                         [c.timestamp for c in full])

    def test_restart_indicator_and_signal_match_uninterrupted_session(self):
        # A distinct earlier regime makes any truncated EMA seed observable.
        prices = [200.0] * 240 + [100.0 + i * 0.01 for i in range(135)]
        full = session(self.start, prices)
        restart_at = 300
        preload = select_completed_preload(
            [], full[:restart_at], session_date=self.day,
            current_minute=self.start + timedelta(minutes=restart_at))
        self.assertEqual(preload, full[:restart_at])
        for minute in (300, 301, 320, 374):
            stream = preload + full[restart_at:minute + 1]
            uninterrupted = evaluate(full[:minute + 1],
                                     session_date=self.day, is_index=True)
            resumed = evaluate(stream, session_date=self.day, is_index=True)
            self.assertEqual(resumed["signal"], uninterrupted["signal"])
            self.assertEqual(resumed["trend_5m"], uninterrupted["trend_5m"])
            self.assertEqual(resumed["momentum"], uninterrupted["momentum"])
            self.assertEqual(resumed["ema9"], uninterrupted["ema9"])
            self.assertEqual(resumed["ema20"], uninterrupted["ema20"])

    def test_restart_preload_excludes_forming_minute(self):
        full = session(self.start, [100 + i * 0.1 for i in range(100)])
        selected = select_completed_preload(
            [], full, session_date=self.day,
            current_minute=self.start + timedelta(minutes=99))
        self.assertEqual(selected, full[:99])


if __name__ == "__main__":
    unittest.main()
