"""Offline checks for isolated real CandleManager tick ingestion."""
import unittest
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from isolated_live_tick_candles import IsolatedTickCandles, extract_tick

IST = ZoneInfo("Asia/Kolkata")
KEY = "ISOLATED_ONLY"


def event(ts, price, key=KEY):
    return {"feeds": {key: {"ltpc": {"ltp": price, "ltt": str(int(ts.timestamp() * 1000))}}}}


class IsolatedTickTests(unittest.TestCase):
    def test_rejects_nonmarket_and_invalid_ticks(self):
        base = datetime.now(IST)
        for bad in ({}, {"type": "heartbeat"}, event(base, 0),
                    event(base, float("nan")), event(base, 100, "OTHER"),
                    {"feeds": {KEY: {"ltpc": {"ltp": 100, "ltt": "invalid"}}}}):
            with self.subTest(value=str(bad)[:50]):
                self.assertIsNone(extract_tick(bad, KEY))

    def test_boolean_price_and_timestamp_are_not_market_ticks(self):
        now = datetime.now(IST)
        stamp = int(now.timestamp() * 1000)
        for ltpc in ({"ltp": True, "ltt": stamp},
                     {"ltp": 100, "ltt": True},
                     {"ltp": 100, "ltt": 1234.5}):
            self.assertIsNone(extract_tick({"feeds": {KEY: {"ltpc": ltpc}}}, KEY))

    def test_nested_upstox_v3_ltpc_feed_shapes(self):
        now = datetime.now(IST)
        ltpc = {"ltp": 123.5, "ltt": str(int(now.timestamp() * 1000))}
        for feed in ({"ltpc": ltpc},
                     {"ltpcFeed": {"ltpc": ltpc}},
                     {"fullFeed": {"marketFF": {"ltpc": ltpc}}}):
            with self.subTest(feed=repr(feed)):
                self.assertEqual(extract_tick({"feeds": {KEY: feed}}, KEY)[0], 123.5)

    def test_rolls_minutes_without_backwards_tick(self):
        now = datetime.now(IST).replace(second=0, microsecond=0)
        a, b = now - timedelta(minutes=2), now - timedelta(minutes=1)
        adapter = IsolatedTickCandles(KEY)
        self.assertTrue(adapter.on_message(event(a, 100)))
        self.assertTrue(adapter.on_message(event(b, 102)))
        self.assertTrue(adapter.on_message(event(a, 99)))
        history, active = adapter.manager.recovery_snapshot(KEY)
        self.assertEqual([c.timestamp for c in history], [a.replace(tzinfo=None)])
        self.assertEqual(active, b.replace(tzinfo=None))
        self.assertEqual(adapter.manager.current[KEY]["candle"].close, 102)
        self.assertEqual(adapter.accepted, 3)
        self.assertEqual(adapter.rejected, 0)

    def test_rejected_payload_does_not_mutate_state(self):
        adapter = IsolatedTickCandles(KEY)
        self.assertFalse(adapter.on_message({"type": "heartbeat"}))
        self.assertEqual(adapter.accepted, 0)
        self.assertEqual(adapter.rejected, 1)
        self.assertEqual(adapter.manager.recovery_snapshot(KEY), ([], None))


if __name__ == "__main__":
    unittest.main()
