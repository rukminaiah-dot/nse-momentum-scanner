import unittest
from datetime import datetime, timedelta
from types import SimpleNamespace
from zoneinfo import ZoneInfo

from v2.backend.experimental_15m_index_trend import (
    INDEX_INSTRUMENTS, _paper_signal, _parse_rows, evaluate_index, run,
)

IST = ZoneInfo("Asia/Kolkata")


def history(days=21):
    rows = []
    day = datetime(2026, 8, 3)
    sessions = []
    while len(sessions) < days:
        if day.weekday() < 5:
            sessions.append(day)
        day += timedelta(days=1)
    for n, session in enumerate(sessions):
        for slot in range(25):
            stamp = session.replace(hour=9, minute=15) + timedelta(minutes=15 * slot)
            close = 100 + n * 0.2 + slot * 0.03
            rows.append({"timestamp": stamp, "open": close - .05,
                         "high": close + .1, "low": close - .1,
                         "close": close})
    return rows


class FakeApi:
    def __init__(self, historical, current):
        self.historical = historical
        self.current = current
        self.historical_calls = []
        self.intraday_calls = []

    def get_historical_candle_data1(self, *args):
        self.historical_calls.append(args)
        return SimpleNamespace(data=SimpleNamespace(candles=self.historical))

    def get_intra_day_candle_data(self, *args):
        self.intraday_calls.append(args)
        return SimpleNamespace(data=SimpleNamespace(candles=self.current))


class ExperimentalIndexTrendTests(unittest.TestCase):
    def test_standard_bullish_oversold_cross_returns_paper_buy(self):
        signal = _paper_signal(
            ema20=110, ema50=100, sma21=100,
            k_previous=10, d_previous=15, k_current=18, d_current=16,
            candle={"open": 105, "high": 110, "low": 104, "close": 109.8},
            previous_bars=[{"high": 108, "low": 103},
                           {"high": 109, "low": 104},
                           {"high": 107, "low": 102}],
        )
        self.assertEqual(signal, "PAPER_BUY")

    def test_standard_bearish_overbought_cross_returns_paper_sell(self):
        signal = _paper_signal(
            ema20=90, ema50=100, sma21=101,
            k_previous=90, d_previous=85, k_current=82, d_current=84,
            candle={"open": 105, "high": 106, "low": 100, "close": 100.1},
            previous_bars=[{"high": 108, "low": 102},
                           {"high": 109, "low": 101},
                           {"high": 107, "low": 103}],
        )
        self.assertEqual(signal, "PAPER_SELL")

    def test_cross_outside_standard_stoch_rsi_zone_waits(self):
        signal = _paper_signal(
            ema20=110, ema50=100, sma21=100,
            k_previous=25, d_previous=30, k_current=35, d_current=32,
            candle={"open": 105, "high": 110, "low": 104, "close": 109.8},
            previous_bars=[{"high": 108, "low": 103},
                           {"high": 109, "low": 104},
                           {"high": 107, "low": 102}],
        )
        self.assertEqual(signal, "WAIT")

    def test_parse_rows_rejects_naive_and_invalid_ohlc(self):
        rows = [
            ["2026-10-22T09:15:00+05:30", 100, 101, 99, 100.5, 0],
            ["2026-10-22T09:30:00", 100, 101, 99, 100.5, 0],
            ["2026-10-22T09:45:00+05:30", 100, 99, 101, 100.5, 0],
        ]
        parsed = _parse_rows(rows)
        self.assertEqual(len(parsed), 1)
        self.assertEqual(parsed[0]["timestamp"], datetime(2026, 10, 22, 9, 15))

    def test_requires_more_than_twenty_prior_sessions(self):
        bars = history(20)
        now = datetime(2026, 10, 22, 10, 15, tzinfo=IST)
        result = evaluate_index("NIFTY 50", bars, now=now)
        self.assertEqual(result["signal"], "WAIT")
        self.assertEqual(result["reason"], "INSUFFICIENT_21_PRIOR_SESSIONS")

    def test_partial_prior_session_does_not_count_toward_history(self):
        bars = history(21)
        bars.pop(0)
        now = datetime(2026, 10, 22, 10, 15, tzinfo=IST)
        result = evaluate_index("NIFTY 50", bars, now=now)
        self.assertEqual(result["reason"], "INSUFFICIENT_21_PRIOR_SESSIONS")
        self.assertEqual(result["prior_session_count"], 20)

    def test_requires_completed_current_session_candle(self):
        bars = history(21)
        now = datetime(2026, 10, 22, 9, 29, tzinfo=IST)
        result = evaluate_index("NIFTY 50", bars, now=now)
        self.assertEqual(result["reason"], "NO_COMPLETED_CURRENT_SESSION_CANDLE")

    def test_upstox_v3_calls_are_read_only_and_correctly_parameterized(self):
        now = datetime(2026, 10, 22, 10, 16, tzinfo=IST)
        historical_rows = [
            [bar["timestamp"].replace(tzinfo=IST).isoformat(),
             bar["open"], bar["high"], bar["low"], bar["close"], 0]
            for bar in history(21)
        ]
        current_rows = [
            ["2026-10-22T09:15:00+05:30", 104, 104.2, 103.9, 104.1, 0],
            ["2026-10-22T09:30:00+05:30", 104.1, 104.3, 104, 104.2, 0],
            ["2026-10-22T09:45:00+05:30", 104.2, 104.4, 104.1, 104.3, 0],
            ["2026-10-22T10:00:00+05:30", 104.3, 104.5, 104.2, 104.4, 0],
            ["2026-10-22T10:15:00+05:30", 104.4, 104.8, 104.3, 104.7, 0],
        ]
        api = FakeApi(historical_rows, current_rows)
        result = run(now=now, api=api, lookback_days=27)
        self.assertEqual(result["mode"], "PAPER")
        self.assertEqual(len(result["indices"]), 3)
        self.assertEqual(len(api.historical_calls), 3)
        self.assertEqual(len(api.intraday_calls), 3)
        self.assertTrue(all((datetime.fromisoformat(call[3]) - datetime.fromisoformat(call[4])).days < 28 for call in api.historical_calls))
        for symbol, key in INDEX_INSTRUMENTS.items():
            self.assertIn((key, "minutes", "15"), api.intraday_calls)
        self.assertTrue(all(row["signal"] in {"WAIT", "PAPER_BUY", "PAPER_SELL"}
                            for row in result["indices"]))
        self.assertTrue(all(row.get("sma21_session_close") is not None
                            for row in result["indices"]))
        self.assertFalse(any("order" in name.lower() for name in dir(api)))

    def test_ninety_day_history_is_split_into_limit_safe_windows(self):
        now = datetime(2026, 10, 22, 10, 16, tzinfo=IST)
        api = FakeApi([], [])
        run(now=now, api=api, lookback_days=90)
        self.assertEqual(len(api.historical_calls), 12)
        self.assertEqual(len(api.intraday_calls), 3)
        for symbol, key in INDEX_INSTRUMENTS.items():
            calls = [call for call in api.historical_calls if call[0] == key]
            self.assertEqual(len(calls), 4)
            windows = sorted((datetime.fromisoformat(call[4]).date(),
                              datetime.fromisoformat(call[3]).date())
                             for call in calls)
            self.assertEqual(windows[0][0], now.date() - timedelta(days=91))
            self.assertEqual(windows[-1][1], now.date() - timedelta(days=1))
            for start, end in windows:
                self.assertLess((end - start).days, 28)
            for earlier, later in zip(windows, windows[1:]):
                self.assertEqual(earlier[1] + timedelta(days=1), later[0])

    def test_rejects_duplicate_15m_timestamps(self):
        bars = history(21)
        bars.extend([dict(bars[-1]), dict(bars[-1])])
        now = datetime(2026, 10, 22, 10, 15, tzinfo=IST)
        result = evaluate_index("NIFTY 50", bars, now=now)
        self.assertEqual(result["reason"], "DUPLICATE_15M_CANDLES")


if __name__ == "__main__":
    unittest.main()
