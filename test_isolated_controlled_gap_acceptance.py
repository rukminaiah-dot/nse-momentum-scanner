"""Offline controlled acceptance: no websocket, network, or credentials."""
import unittest
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from isolated_stream_recovery import IsolatedStreamRecovery
from isolated_controlled_gap_acceptance import controlled_gap_acceptance

IST = ZoneInfo("Asia/Kolkata")
KEY = "CONTROLLED_ONLY"


class ControlledGapTests(unittest.TestCase):
    def test_real_tick_state_and_broker_backed_missing_minute(self):
        now = datetime.now(IST).replace(second=0, microsecond=0)
        minutes = [now - timedelta(minutes=n) for n in (3, 2, 1)]
        if minutes[0].date() != now.date():
            self.skipTest("IST day boundary")
        calls = []
        def fetch(key):
            calls.append(key)
            return [[minute.isoformat(), 100, 101, 99, 100, 5]
                    for minute in minutes]
        bridge = IsolatedStreamRecovery(KEY, fetch, min_request_spacing=0.001)
        tick = {"feeds": {KEY: {"ltpc": {
            "ltp": 105, "ltt": str(int(now.timestamp() * 1000))}}}}
        self.assertTrue(bridge.on_message(tick))
        passed, reason = controlled_gap_acceptance(bridge)
        self.assertTrue(passed, reason)
        self.assertEqual(calls, [KEY, KEY])
        self.assertEqual(bridge.worker.status()["verified_insertions"], 1)
        history, active = bridge.candles.manager.recovery_snapshot(KEY)
        self.assertEqual(active, now.replace(tzinfo=None))
        self.assertEqual(len(history), 1)
        self.assertEqual(bridge.candles.manager.current[KEY]["candle"].close, 105)

    def test_no_tick_never_fetches_broker(self):
        calls = []
        bridge = IsolatedStreamRecovery(KEY, lambda key: calls.append(key) or [])
        self.assertFalse(controlled_gap_acceptance(bridge)[0])
        self.assertEqual(calls, [])


if __name__ == "__main__":
    unittest.main()
