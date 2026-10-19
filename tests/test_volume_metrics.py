import unittest
from datetime import datetime, timedelta
from types import SimpleNamespace

from v2.backend.volume_metrics import verified_relative_volume


class VerifiedRelativeVolumeTests(unittest.TestCase):
    def candles(self, volumes, start=None):
        start = start or datetime(2026, 10, 19, 10, 0)
        return [SimpleNamespace(timestamp=start + timedelta(minutes=i), volume=value)
                for i, value in enumerate(volumes)]

    def test_uses_latest_candle_against_prior_19_actual_bars(self):
        result = verified_relative_volume(self.candles([100] * 19 + [150]))
        self.assertEqual(result['relative_volume'], 1.5)
        self.assertEqual(result['current_volume'], 150)
        self.assertEqual(result['baseline_volume'], 100)
        self.assertEqual(result['reference_bars'], 19)

    def test_missing_minute_fails_closed(self):
        rows = self.candles([100] * 20)
        rows[-2].timestamp += timedelta(minutes=1)
        self.assertIsNone(verified_relative_volume(rows))

    def test_cross_session_comparison_fails_closed(self):
        rows = self.candles([100] * 20)
        rows[0].timestamp -= timedelta(days=1)
        self.assertIsNone(verified_relative_volume(rows))

    def test_zero_or_invalid_baseline_fails_closed(self):
        self.assertIsNone(verified_relative_volume(self.candles([0] * 20)))
        rows = self.candles([100] * 19 + [float('nan')])
        self.assertIsNone(verified_relative_volume(rows))

    def test_incomplete_warmup_fails_closed(self):
        self.assertIsNone(verified_relative_volume(self.candles([100] * 19)))


if __name__ == '__main__':
    unittest.main()
