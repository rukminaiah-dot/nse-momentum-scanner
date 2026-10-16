"""Offline-only checks for the isolated scanner decision candidate."""
import unittest
from datetime import datetime, timedelta
from v2.backend.candles import Candle
from v2.backend.offline_signal_parity import evaluate, five_minute_trend


def history(count=30, direction=1):
    start = datetime(2026, 10, 16, 9, 15)
    result = []
    for i in range(count):
        candle = Candle(100 + direction * i * 0.1, 100)
        candle.timestamp = start + timedelta(minutes=i)
        result.append(candle)
    return result


class OfflineSignalParityTests(unittest.TestCase):
    def test_warmup_is_blocked(self):
        result = evaluate(history(19), session_date=datetime(2026, 10, 16).date())
        self.assertEqual(result["reason"], "WARMUP")

    def test_missing_minute_blocks(self):
        bars = history()
        bars[-1].timestamp += timedelta(minutes=1)
        result = evaluate(bars, session_date=datetime(2026, 10, 16).date())
        self.assertEqual(result["reason"], "MISSING_MINUTE")

    def test_overnight_momentum_blocks(self):
        result = evaluate(history(), session_date=datetime(2026, 10, 17).date())
        self.assertEqual(result["reason"], "OVERNIGHT_GAP")

    def test_index_uptrend_is_directional(self):
        result = evaluate(history(), session_date=datetime(2026, 10, 16).date(),
                          is_index=True)
        self.assertEqual(result["signal"], "BUY")
        self.assertEqual(result["trend_5m"], "BULLISH")

    def test_index_downtrend_is_directional(self):
        result = evaluate(history(direction=-1),
                          session_date=datetime(2026, 10, 16).date(), is_index=True)
        self.assertEqual(result["signal"], "SELL")

    def test_stock_rvol_computed_without_orders(self):
        result = evaluate(history(), session_date=datetime(2026, 10, 16).date(),
                          is_stock=True)
        self.assertEqual(result["rvol"], 1.0)
        self.assertIn(result["signal"], ("BUY", "SELL", "HOLD"))

    def test_incomplete_five_minute_bucket_is_not_used(self):
        bars = history(29)
        self.assertEqual(five_minute_trend(bars), "BULLISH")


if __name__ == "__main__":
    unittest.main()
