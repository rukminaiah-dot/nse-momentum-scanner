import unittest
from datetime import datetime, timedelta
from types import SimpleNamespace

from v2.backend.volume_metrics import (\n    verified_relative_volume, completed_intraday_bars,\n    verified_same_slot_relative_volume, confirmed_range_breakout,\n)


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

    def test_15m_aggregation_skips_partial_or_gapped_groups(self):
        rows = []
        start = datetime(2026, 10, 19, 9, 15)
        for i in range(30):
            if i == 7:
                continue
            stamp = start + timedelta(minutes=i)
            rows.append(SimpleNamespace(
                timestamp=stamp, open=100, high=101, low=99, close=100,
                volume=10,
            ))
        result = completed_intraday_bars(rows, 15)
        self.assertEqual([bar["timestamp"] for bar in result],
                         [datetime(2026, 10, 19, 9, 30)])

    def test_same_slot_rvol_uses_twenty_prior_sessions(self):
        current = {"timestamp": datetime(2026, 10, 19, 10, 0),
                   "open": 100, "close": 101, "volume": 150}
        rows = []
        for i in range(1, 21):
            stamp = current["timestamp"] - timedelta(days=i)
            rows.append([stamp.isoformat(), 100, 101, 99, 100, 100, 0])
        rows.append([(current["timestamp"] - timedelta(days=1)).replace(
            minute=15).isoformat(), 100, 101, 99, 100, 9999, 0])
        result = verified_same_slot_relative_volume(current, rows, 20)
        self.assertEqual(result["relative_volume"], 1.5)
        self.assertEqual(result["baseline_volume"], 100)
        self.assertEqual(result["slot"], "10:00")
        self.assertEqual(result["candle_direction"], "BULLISH")

    def test_missing_prior_session_volume_fails_closed(self):
        current = {"timestamp": datetime(2026, 10, 19, 10, 0),
                   "open": 100, "close": 101, "volume": 150}
        rows = []
        for i in range(1, 20):
            stamp = current["timestamp"] - timedelta(days=i)
            rows.append([stamp.isoformat(), 100, 101, 99, 100, 100, 0])
        self.assertIsNone(verified_same_slot_relative_volume(current, rows, 20))

    def test_breakout_requires_four_contiguous_completed_15m_bars(self):
        start = datetime(2026, 10, 19, 9, 15)
        bars = []
        for i in range(4):
            close = 102 if i == 3 else 100
            bars.append({"timestamp": start + timedelta(minutes=15 * i),
                         "open": 100, "high": close, "low": 100,
                         "close": close})
        self.assertTrue(confirmed_range_breakout(bars, "BUY"))
        bars[-1]["timestamp"] += timedelta(minutes=15)
        self.assertFalse(confirmed_range_breakout(bars, "BUY"))


if __name__ == '__main__':
    unittest.main()
