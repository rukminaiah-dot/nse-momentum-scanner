"""Offline restart/preload replay: real scanner selection rule, no scanner import.

These checks demonstrate that the scanner's 60-bar startup preload is an
independent source of indicator drift even when manager retention is unlimited.
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

    def test_restart_preload_has_only_latest_sixty_even_without_retention_cap(self):
        full = session(self.start, [100 + i * 0.03 for i in range(300)])
        cutoff = self.start + timedelta(minutes=300)
        selected = select_completed_preload([], list(reversed(full)),
                                            session_date=self.day,
                                            current_minute=cutoff)
        self.assertEqual(len(selected), 60)
        self.assertEqual(selected[0].timestamp, full[240].timestamp)
        self.assertEqual(selected[-1].timestamp, full[-1].timestamp)

    def test_restart_indicator_drift_with_identical_subsequent_candles(self):
        # Abrupt earlier price regime gives the unlimited EMA a different
        # initial seed from the 60-bar restart preload.
        prices = ([200.0] * 240 + [100.0 + i * 0.01 for i in range(135)])
        full = session(self.start, prices)
        restart_at = 300
        preload = select_completed_preload(
            [], full[:restart_at], session_date=self.day,
            current_minute=self.start + timedelta(minutes=restart_at))
        self.assertEqual(len(preload), 60)
        for minute in (300, 301, 320, 374):
            # Reconstruct exact post-restart stream for each checkpoint.
            stream = preload + full[restart_at:minute + 1]
            unlimited = evaluate(full[:minute + 1], session_date=self.day,
                                 is_index=True)
            resumed = evaluate(stream, session_date=self.day, is_index=True)
            self.assertNotEqual(unlimited["signal"], "BLOCKED")
            self.assertNotEqual(resumed["signal"], "BLOCKED")
            self.assertEqual(unlimited["trend_5m"], resumed["trend_5m"])
            self.assertEqual(unlimited["momentum"], resumed["momentum"])
            if minute == 300:
                self.assertNotEqual(unlimited["ema20"], resumed["ema20"])

    def test_restart_preload_excludes_forming_minute(self):
        full = session(self.start, [100 + i * 0.1 for i in range(100)])
        selected = select_completed_preload(
            [], full, session_date=self.day,
            current_minute=self.start + timedelta(minutes=99))
        self.assertEqual(selected[-1].timestamp,
                         self.start + timedelta(minutes=98))


if __name__ == "__main__":
    unittest.main()
