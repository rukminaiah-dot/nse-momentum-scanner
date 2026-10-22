"""No-network tests for experimental Upstox 15m adapter."""
import unittest
from datetime import datetime, timedelta
from types import SimpleNamespace
from v2.backend.experimental_15m_upstox_runner import fetch_symbol, run


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

    def test_historical_candles_are_cached_within_scan_day(self):
        now = datetime(2026, 10, 21, 10, 8)
        api = FakeApi([row(datetime(2026, 10, 20, 10))], [])
        cache = {}
        fetch_symbol(api, "NSE_EQ|TEST", now=now, historical_cache=cache)
        fetch_symbol(api, "NSE_EQ|TEST", now=now, historical_cache=cache)
        self.assertEqual(sum(1 for kind, _ in api.calls if kind == "history"), 1)
        self.assertEqual(sum(1 for kind, _ in api.calls if kind == "intraday"), 2)

    def test_run_does_not_need_live_broker(self):
        now = datetime(2026, 10, 21, 10, 8)
        result = run(limit=1, now=now, api=FakeApi([], []))
        self.assertEqual(result["mode"], "PAPER")
        self.assertEqual(result["selected_count"], 0)
        self.assertEqual(result["requested_count"], 1)


if __name__ == "__main__":
    unittest.main()
