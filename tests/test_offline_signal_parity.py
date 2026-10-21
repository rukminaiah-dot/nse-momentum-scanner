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

    def test_secondary_index_uses_primary_market_regime(self):
        bars = history()
        primary = evaluate(bars, session_date=datetime(2026, 10, 16).date(),
                           is_index=True)
        secondary = evaluate(bars, session_date=datetime(2026, 10, 16).date(),
                             is_index=True, is_primary_index=False,
                             nifty_market="BEARISH")
        self.assertEqual(primary["market"], "BULLISH")
        self.assertEqual(secondary["market"], "BEARISH")
        self.assertEqual(secondary["signal"], "BUY")

    def test_stock_uses_supplied_primary_market_regime(self):
        result = evaluate(history(), session_date=datetime(2026, 10, 16).date(),
                          is_stock=True, nifty_market="BEARISH")
        self.assertEqual(result["market"], "BEARISH")

    def test_reject_ambiguous_instrument_classification(self):
        with self.assertRaises(ValueError):
            evaluate(history(), session_date=datetime(2026, 10, 16).date(),
                     is_index=True, is_stock=True)

    def test_sixty_bar_cap_can_flip_both_index_classes(self):
        from v2.backend.offline_signal_parity import evaluate
        for direction, seed, expected in ((1, 150.0, "BUY"),
                                           (-1, 50.0, "SELL")):
            prices = [seed] * 340 + [100 + direction * i * 0.01
                                     for i in range(60)]
            bars = []
            start = datetime(2026, 10, 16, 9, 15)
            for i, price in enumerate(prices):
                candle = Candle(price, 100)
                candle.timestamp = start + timedelta(minutes=i)
                bars.append(candle)
            for primary in (True, False):
                with self.subTest(direction=direction, primary=primary):
                    opts = dict(session_date=start.date(), is_index=True,
                                is_primary_index=primary)
                    self.assertEqual(evaluate(bars, **opts)["signal"], "HOLD")
                    self.assertEqual(evaluate(bars[-60:], **opts)["signal"],
                                     expected)

    def test_five_minute_trend_requires_three_complete_buckets(self):
        bars = history(14)
        self.assertEqual(five_minute_trend(bars), "NEUTRAL")
        self.assertEqual(five_minute_trend(history(15)), "BULLISH")

    def test_five_minute_trend_ignores_incomplete_latest_bucket(self):
        bars = history(16)
        self.assertEqual(five_minute_trend(bars), "BULLISH")
        bars[-1].close = -1000
        self.assertEqual(five_minute_trend(bars), "BULLISH")

    def test_realistic_375_minute_sessions_preserve_index_warmup(self):
        """A full previous trading session cannot satisfy today's index warmup."""
        previous = history(375)
        for candle in previous:
            candle.timestamp -= timedelta(days=1)
        today = history(20)
        for today_count, expected_reason in ((19, "WARMUP"), (20, None)):
            for cap in (60, 200):
                with self.subTest(today_count=today_count, cap=cap):
                    bars = (previous + today[:today_count])[-cap:]
                    result = evaluate(bars, session_date=today[0].timestamp.date(),
                                      is_index=True)
                    self.assertEqual(result["reason"], expected_reason)
                    if today_count == 20:
                        expected = evaluate(today, session_date=today[0].timestamp.date(),
                                            is_index=True)
                        self.assertEqual(result["signal"], expected["signal"])
                        self.assertEqual(result["ema9"], expected["ema9"])
                        self.assertEqual(result["ema20"], expected["ema20"])

    def test_realistic_375_minute_sessions_do_not_bridge_stock_gap(self):
        previous = history(375)
        for candle in previous:
            candle.timestamp -= timedelta(days=1)
        today = history(6)
        for today_count, expected_reason in ((5, "OVERNIGHT_GAP"),
                                              (6, None)):
            for cap in (60, 200):
                with self.subTest(today_count=today_count, cap=cap):
                    bars = (previous + today[:today_count])[-cap:]
                    result = evaluate(bars, session_date=today[0].timestamp.date(),
                                      is_stock=True)
                    self.assertEqual(result["reason"], expected_reason)

    def test_session_open_missing_minute_blocks_even_with_yesterday_history(self):
        previous = history(375)
        for candle in previous:
            candle.timestamp -= timedelta(days=1)
        today = history(6)
        today[3].timestamp += timedelta(minutes=1)
        for cap in (60, 200):
            with self.subTest(cap=cap):
                result = evaluate((previous + today)[-cap:],
                                  session_date=today[0].timestamp.date(),
                                  is_stock=True)
                self.assertEqual(result["reason"], "MISSING_MINUTE")

    def test_secondary_index_session_warmup_matches_primary_index(self):
        previous = history(375)
        for candle in previous:
            candle.timestamp -= timedelta(days=1)
        today = history(19)
        for primary in (True, False):
            for cap in (60, 200):
                with self.subTest(primary=primary, cap=cap):
                    result = evaluate((previous + today)[-cap:],
                                      session_date=today[0].timestamp.date(),
                                      is_index=True, is_primary_index=primary)
                    self.assertEqual(result["reason"], "WARMUP")


if __name__ == "__main__":
    unittest.main()
