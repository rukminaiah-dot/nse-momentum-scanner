"""Safety tests for isolated 15-minute research strategy."""
import unittest
from datetime import datetime, timedelta
from unittest.mock import patch
from v2.backend.experimental_15m_stoch_rsi import evaluate


class TestExperimental15m(unittest.TestCase):
    def setUp(self):
        start = datetime(2026, 10, 19, 9, 15)
        self.bars = [
            {"timestamp": start + timedelta(days=i // 25, minutes=15 * (i % 25)),
             "open": 100 + i * .1, "high": 101 + i * .1,
             "low": 99 + i * .1, "close": 100.2 + i * .1,
             "volume": 200}
            for i in range(60)
        ]
        self.now = self.bars[-1]["timestamp"] + timedelta(minutes=15)

    def test_requires_verified_volume(self):
        self.assertEqual(evaluate(self.bars, now=self.now,
                                  same_slot_average_volume=None)["reason"],
                         "MISSING_VERIFIED_20_SESSION_VOLUME_BASELINE")

    def test_rejects_incomplete_candle(self):
        self.assertEqual(evaluate(self.bars, now=self.now - timedelta(minutes=1),
                                  same_slot_average_volume=100)["reason"],
                         "STALE_OR_INCOMPLETE_15M_CANDLE")

    def test_rejects_stale_candle(self):
        self.assertEqual(evaluate(self.bars, now=self.now + timedelta(minutes=19),
                                  same_slot_average_volume=100)["reason"],
                         "STALE_OR_INCOMPLETE_15M_CANDLE")

    def test_rejects_missing_candle(self):
        self.bars[-3]["timestamp"] -= timedelta(minutes=1)
        self.assertEqual(evaluate(self.bars, now=self.now,
                                  same_slot_average_volume=100)["reason"],
                         "NONCONTIGUOUS_15M_CANDLES")

    def test_overnight_history_allowed(self):
        # 25 completed bars per session; the 50-bar EMA must span days.
        start = datetime(2026, 10, 20, 9, 15)
        for i, bar in enumerate(self.bars):
            day = 0 if i < 25 else 1 if i < 50 else 2
            slot = i if i < 25 else i - 25 if i < 50 else i - 50
            bar["timestamp"] = start + timedelta(days=day, minutes=15 * slot)
        self.now = self.bars[-1]["timestamp"] + timedelta(minutes=15)
        result = evaluate(self.bars, now=self.now, same_slot_average_volume=100)
        self.assertNotEqual(result["reason"], "NONCONTIGUOUS_15M_CANDLES")

    def test_no_cross_session_breakout(self):
        start = datetime(2026, 10, 20, 9, 15)
        self.bars = self.bars[:53]
        for i, bar in enumerate(self.bars):
            day, slot = divmod(i, 25)
            bar["timestamp"] = start + timedelta(days=day, minutes=15 * slot)
        self.now = self.bars[-1]["timestamp"] + timedelta(minutes=15)
        self.assertEqual(evaluate(self.bars, now=self.now,
                         same_slot_average_volume=100)["reason"],
                         "INSUFFICIENT_SAME_SESSION_BREAKOUT_BARS")

    def _signal_bars(self, direction):
        bars = [dict(bar) for bar in self.bars]
        for bar in bars[-4:-1]:
            if direction == "buy":
                bar.update({"open": 99.5, "high": 100.5, "low": 99.0, "close": 100.0})
            else:
                bar.update({"open": 100.0, "high": 101.0, "low": 99.5, "close": 100.0})
        if direction == "buy":
            bars[-1].update({"open": 100.0, "high": 102.0, "low": 99.0, "close": 101.5, "volume": 200})
        else:
            bars[-1].update({"open": 100.0, "high": 101.0, "low": 98.0, "close": 98.5, "volume": 200})
        return bars

    def test_buy_requires_oversold_bullish_kd_cross(self):
        bars = self._signal_bars("buy")
        with patch("v2.backend.experimental_15m_stoch_rsi._ema",
                   side_effect=[[100, 101], [99, 100]]), patch("v2.backend.experimental_15m_stoch_rsi._stoch_rsi",
                   return_value=([10, 18], [15, 17])):
            result = evaluate(bars, now=bars[-1]["timestamp"] + timedelta(minutes=15),
                              same_slot_average_volume=100)
        self.assertEqual(result["signal"], "PAPER_BUY")
        self.assertEqual(result["details"]["trend"], "BULLISH")
        self.assertEqual(result["details"]["ema20"], 101)
        self.assertEqual(result["details"]["ema50"], 100)
        self.assertEqual(result["details"]["stoch_k"], 18)
        self.assertEqual(result["details"]["stoch_d"], 17)

    def test_buy_cross_above_oversold_is_wait(self):
        bars = self._signal_bars("buy")
        with patch("v2.backend.experimental_15m_stoch_rsi._ema",
                   side_effect=[[100, 101], [99, 100]]), patch("v2.backend.experimental_15m_stoch_rsi._stoch_rsi",
                   return_value=([10, 25], [15, 20])):
            result = evaluate(bars, now=bars[-1]["timestamp"] + timedelta(minutes=15),
                              same_slot_average_volume=100)
        self.assertEqual(result["signal"], "WAIT")

    def test_sell_requires_overbought_bearish_kd_cross(self):
        bars = self._signal_bars("sell")
        with patch("v2.backend.experimental_15m_stoch_rsi._ema",
                   side_effect=[[100, 99], [101, 100]]), patch("v2.backend.experimental_15m_stoch_rsi._stoch_rsi",
                   return_value=([90, 82], [85, 83])):
            result = evaluate(bars, now=bars[-1]["timestamp"] + timedelta(minutes=15),
                              same_slot_average_volume=100)
        self.assertEqual(result["signal"], "PAPER_SELL")

    def test_sell_cross_below_overbought_is_wait(self):
        bars = self._signal_bars("sell")
        with patch("v2.backend.experimental_15m_stoch_rsi._ema",
                   side_effect=[[100, 99], [101, 100]]), patch("v2.backend.experimental_15m_stoch_rsi._stoch_rsi",
                   return_value=([90, 75], [85, 80])):
            result = evaluate(bars, now=bars[-1]["timestamp"] + timedelta(minutes=15),
                              same_slot_average_volume=100)
        self.assertEqual(result["signal"], "WAIT")

    def test_no_live_orders(self):
        result = evaluate(self.bars, now=self.now, same_slot_average_volume=100)
        self.assertEqual(result["mode"], "PAPER")
        self.assertIn(result["signal"], {"WAIT", "PAPER_BUY", "PAPER_SELL"})


if __name__ == "__main__":
    unittest.main()
