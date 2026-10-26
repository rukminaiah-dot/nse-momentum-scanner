"""No-network tests for experimental Upstox 15m adapter."""
import unittest
from datetime import datetime, timedelta
from types import SimpleNamespace
from v2.backend.experimental_15m_upstox_runner import (fetch_symbol, run, previous_session_close, _call_with_retry, _safe_error_label)


class FakeApi:
    def __init__(self, historical, intraday):
        self.historical = historical
        self.intraday = intraday
        self.calls = []

    def get_historical_candle_data1(self, *args):
        self.calls.append(("history", args))
        return SimpleNamespace(data=SimpleNamespace(candles=self.historical))

    def get_intra_day_candle_data(self, *args):
        self.calls.append(("intraday", args))
        return SimpleNamespace(data=SimpleNamespace(candles=self.intraday))


def row(stamp, volume=100):
    return [stamp.isoformat() + "+05:30", 100, 102, 99, 101, volume]


class TestUpstoxPaperRunner(unittest.TestCase):
    def test_fetch_uses_15m_and_drops_incomplete(self):
        now = datetime(2026, 10, 21, 10, 8)
        api = FakeApi([row(datetime(2026, 10, 20, 10))],
                      [row(datetime(2026, 10, 21, 9, 45)),
                       row(datetime(2026, 10, 21, 10, 0))])
        bars, history = fetch_symbol(api, "NSE_EQ|TEST", now=now)
        self.assertEqual(len(history), 1)
        self.assertEqual(len(bars), 2)
        self.assertEqual(bars[-1]["timestamp"].minute, 45)
        self.assertEqual(api.calls[0][1][1:3], ("minutes", "15"))
        self.assertEqual(api.calls[0][1][3], "2026-10-20")
        self.assertEqual(api.calls[0][1][4], "2026-09-20")
        self.assertEqual(api.calls[1][1][1:3], ("minutes", "15"))

    def test_retries_rate_limit_with_bounded_backoff_and_throttle(self):
        class RateLimit(Exception):
            status = 429

        attempts, delays = [], []

        def request():
            attempts.append(1)
            if len(attempts) == 1:
                raise RateLimit()
            return "ok"

        self.assertEqual(_call_with_retry(request, sleep_fn=delays.append), "ok")
        self.assertEqual(len(attempts), 2)
        self.assertEqual(delays, [0.5, 0.12])

    def test_does_not_retry_authentication_errors(self):
        class Unauthorized(Exception):
            status = 401

        attempts, delays = [], []

        def request():
            attempts.append(1)
            raise Unauthorized()

        with self.assertRaises(Unauthorized):
            _call_with_retry(request, sleep_fn=delays.append)
        self.assertEqual(len(attempts), 1)
        self.assertEqual(delays, [])

    def test_error_label_only_exposes_safe_status_not_message(self):
        class ApiException(Exception):
            status = 401

        exc = ApiException("Authorization: secret-value")
        self.assertEqual(_safe_error_label(exc), "ApiException:401")
        self.assertNotIn("secret-value", _safe_error_label(exc))

    def test_previous_close_uses_verified_final_15m_bar(self):
        history = [
            {"timestamp": datetime(2026, 10, 20, 15, 0), "close": 100},
            {"timestamp": datetime(2026, 10, 20, 15, 15), "close": 102},
            {"timestamp": datetime(2026, 10, 21, 9, 15), "close": 103},
        ]
        self.assertEqual(previous_session_close(history, datetime(2026, 10, 21).date()), 102)
        self.assertIsNone(previous_session_close(history[:1], datetime(2026, 10, 21).date()))

    def test_historical_candles_are_cached_within_scan_day(self):
        now = datetime(2026, 10, 21, 10, 8)
        api = FakeApi([row(datetime(2026, 10, 20, 10))], [])
        cache = {}
        fetch_symbol(api, "NSE_EQ|TEST", now=now, historical_cache=cache)
        fetch_symbol(api, "NSE_EQ|TEST", now=now, historical_cache=cache)
        self.assertEqual(sum(1 for kind, _ in api.calls if kind == "history"), 1)
        self.assertEqual(sum(1 for kind, _ in api.calls if kind == "intraday"), 2)

    def test_run_reports_verified_history_and_completed_intraday_quality(self):
        now = datetime(2026, 10, 21, 10, 8)
        historical = []
        day = now.date() - timedelta(days=30)
        while len(historical) < 20:
            if day.weekday() < 5:
                historical.append(row(datetime.combine(day, datetime.min.time())
                                      + timedelta(minutes=555)))
            day += timedelta(days=1)
        api = FakeApi(historical, [
            row(datetime(2026, 10, 21, 9, 45)),
            row(datetime(2026, 10, 21, 10, 0)),
        ])
        result = run(limit=1, now=now, api=api)
        symbol = next(iter(result["data_quality"]))
        quality = result["data_quality"][symbol]
        self.assertEqual(quality["open_slot_sessions"], 20)
        self.assertTrue(quality["open_slot_baseline_verified"])
        self.assertEqual(quality["completed_intraday_candles"], 1)

    def test_universe_history_is_processed_one_symbol_at_a_time_and_cache_is_bounded(self):
        from unittest.mock import patch
        from v2.backend import experimental_15m_upstox_runner as runner
        now = datetime(2026, 10, 21, 10, 8)
        api = FakeApi([row(datetime(2026, 10, 20, 15, 15))], [])
        original = runner.screen_universe
        sizes = []
        def checked(bars, history, **kwargs):
            sizes.append((len(bars), len(history)))
            return original(bars, history, **kwargs)
        with patch.object(runner, 'screen_universe', side_effect=checked), patch.object(runner, '_REQUEST_PAUSE_SECONDS', 0):
            result = runner.run(limit=12, now=now, api=api)
        self.assertEqual(sizes, [(1, 1)] * 12)
        self.assertLessEqual(len(runner._HISTORICAL_CACHE), 200)
        self.assertTrue(all(isinstance(x, bytes) for x in runner._HISTORICAL_CACHE.data.values()))
        self.assertEqual(result['universe_count'], 12)
        self.assertEqual(len(result['stock_context']), 12)

    def test_run_does_not_need_live_broker(self):
        now = datetime(2026, 10, 21, 10, 8)
        result = run(limit=1, now=now, api=FakeApi([], []))
        self.assertEqual(result["mode"], "PAPER")
        self.assertEqual(result["selected_count"], 0)
        self.assertEqual(result["requested_count"], 1)


if __name__ == "__main__":
    unittest.main()
