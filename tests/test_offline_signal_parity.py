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

    def test_incomplete_last_bucket_cannot_reverse_trend(self):
        bars = history(30)
        for candle in bars[-4:]:
            candle.close = 1.0
        # The 09:40 bucket has five candles, so make it incomplete by
        # dropping its first candle; a four-bar bucket must be ignored.
        bars = [c for c in bars if c.timestamp != datetime(2026, 10, 16, 9, 40)]
        self.assertEqual(five_minute_trend(bars), "BULLISH")

    def test_stock_zero_volume_cannot_confirm_buy(self):
        bars = history()
        for candle in bars:
            candle.volume = 0
        result = evaluate(bars, session_date=datetime(2026, 10, 16).date(),
                          is_stock=True)
        self.assertEqual(result["rvol"], 0.0)
        self.assertNotEqual(result["signal"], "BUY")

    def test_index_excludes_previous_session_from_ema(self):
        bars = history()
        previous = history(25)
        for candle in previous:
            candle.timestamp -= timedelta(days=1)
            candle.close = 500.0
        current = evaluate(bars, session_date=datetime(2026, 10, 16).date(),
                           is_index=True)
        combined = evaluate(previous + bars,
                            session_date=datetime(2026, 10, 16).date(),
                            is_index=True)
        self.assertEqual(current["ema9"], combined["ema9"])
        self.assertEqual(current["ema20"], combined["ema20"])
        self.assertEqual(current["signal"], combined["signal"])

    def test_overnight_stock_ema_can_use_prior_session_history(self):
        bars = history()
        previous = history(25)
        for candle in previous:
            candle.timestamp -= timedelta(days=1)
            candle.close = 500.0
        current = evaluate(bars, session_date=datetime(2026, 10, 16).date(),
                           is_stock=True)
        combined = evaluate(previous + bars,
                            session_date=datetime(2026, 10, 16).date(),
                            is_stock=True)
        self.assertNotEqual(current["ema20"], combined["ema20"])

    def test_index_new_session_requires_twenty_today_bars(self):
        previous = history(30)
        for candle in previous:
            candle.timestamp -= timedelta(days=1)
        today = history(19)
        result = evaluate(previous + today,
                          session_date=datetime(2026, 10, 16).date(),
                          is_index=True)
        self.assertEqual(result, {"signal": "BLOCKED", "reason": "WARMUP"})

    def test_stock_first_six_minutes_can_use_overnight_ema(self):
        previous = history(30)
        for candle in previous:
            candle.timestamp -= timedelta(days=1)
        today = history(6)
        result = evaluate(previous + today,
                          session_date=datetime(2026, 10, 16).date(),
                          is_stock=True)
        self.assertIsNone(result["reason"])
        self.assertIsNotNone(result["ema20"])

    def test_stock_first_five_minutes_block_overnight_momentum(self):
        previous = history(30)
        for candle in previous:
            candle.timestamp -= timedelta(days=1)
        today = history(5)
        result = evaluate(previous + today,
                          session_date=datetime(2026, 10, 16).date(),
                          is_stock=True)
        self.assertEqual(result["reason"], "OVERNIGHT_GAP")

    def test_five_minute_trend_ignores_previous_session_buckets(self):
        previous = history(30, direction=-1)
        for candle in previous:
            candle.timestamp -= timedelta(days=1)
        today = history(15, direction=1)
        self.assertEqual(five_minute_trend(previous + today), "BULLISH")

    def test_five_minute_trend_requires_three_complete_buckets(self):
        bars = history(15)
        bars = [c for c in bars if c.timestamp != datetime(2026, 10, 16, 9, 20)]
        self.assertEqual(five_minute_trend(bars), "NEUTRAL")

    def test_retention_cannot_bypass_index_session_warmup(self):
        previous = history(240)
        for candle in previous:
            candle.timestamp -= timedelta(days=1)
        today = history(19)
        for cap in (60, 200):
            with self.subTest(cap=cap):
                result = evaluate((previous + today)[-cap:],
                                  session_date=datetime(2026, 10, 16).date(),
                                  is_index=True)
                self.assertEqual(result["reason"], "WARMUP")

    def test_retention_cannot_bridge_overnight_stock_momentum(self):
        previous = history(240)
        for candle in previous:
            candle.timestamp -= timedelta(days=1)
        today = history(5)
        for cap in (60, 200):
            with self.subTest(cap=cap):
                result = evaluate((previous + today)[-cap:],
                                  session_date=datetime(2026, 10, 16).date(),
                                  is_stock=True)
                self.assertEqual(result["reason"], "OVERNIGHT_GAP")

    def test_retention_keeps_stock_continuity_after_six_today_bars(self):
        previous = history(240)
        for candle in previous:
            candle.timestamp -= timedelta(days=1)
        today = history(6)
        for cap in (60, 200):
            with self.subTest(cap=cap):
                result = evaluate((previous + today)[-cap:],
                                  session_date=datetime(2026, 10, 16).date(),
                                  is_stock=True)
                self.assertIsNone(result["reason"])


if __name__ == "__main__":
    unittest.main()
