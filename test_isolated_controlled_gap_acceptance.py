"""Offline controlled acceptance: no websocket, network, or credentials."""
import unittest
import threading
from unittest.mock import patch
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
        self.assertEqual(bridge.worker.status()["requested"], 1)
        self.assertEqual(bridge.worker.status()["completed"], 1)
        self.assertEqual(bridge.worker.status()["skipped"], 0)
        history, active = bridge.candles.manager.recovery_snapshot(KEY)
        self.assertEqual(active, now.replace(tzinfo=None))
        self.assertEqual(len(history), 0)
        self.assertEqual(bridge.candles.manager.current[KEY]["candle"].close, 105)

    def test_long_broker_history_recovers_only_one_minute(self):
        now = datetime.now(IST).replace(second=0, microsecond=0)
        if (now - timedelta(minutes=70)).date() != now.date():
            self.skipTest("IST day boundary")
        minutes = [now - timedelta(minutes=n) for n in range(70, 0, -1)]
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
        self.assertEqual(bridge.worker.status()["verified_insertions"], 1)
        self.assertEqual(len(calls), 2)
        history, active = bridge.candles.manager.recovery_snapshot(KEY)
        self.assertEqual(active, now.replace(tzinfo=None))
        self.assertEqual(len(history), 1)

    def test_changed_broker_candle_does_not_pass(self):
        now = datetime.now(IST).replace(second=0, microsecond=0)
        minutes = [now - timedelta(minutes=n) for n in (3, 2, 1)]
        if minutes[0].date() != now.date():
            self.skipTest("IST day boundary")
        calls = []
        def fetch(key):
            calls.append(key)
            # The omitted minute is the second-oldest historical minute.
            # Change its close on the worker's second authenticated fetch.
            return [[minute.isoformat(), 100, 101, 99,
                     (100.5 if len(calls) == 2 and minute == minutes[1] else 100), 5]
                    for minute in minutes]
        bridge = IsolatedStreamRecovery(KEY, fetch, min_request_spacing=0.001)
        tick = {"feeds": {KEY: {"ltpc": {
            "ltp": 105, "ltt": str(int(now.timestamp() * 1000))}}}}
        self.assertTrue(bridge.on_message(tick))
        passed, reason = controlled_gap_acceptance(bridge)
        self.assertFalse(passed)
        self.assertEqual(reason, "broker candle values differ")
        self.assertEqual(len(calls), 2)
        self.assertEqual(bridge.candles.manager.recovery_snapshot(KEY)[0], [])

    def test_pending_worker_keeps_anchors_until_process_exit(self):
        now = datetime.now(IST).replace(second=0, microsecond=0)
        minutes = [now - timedelta(minutes=n) for n in (3, 2, 1)]
        if minutes[0].date() != now.date():
            self.skipTest("IST day boundary")
        entered = threading.Event()
        release = threading.Event()
        calls = []
        def fetch(key):
            calls.append(key)
            if len(calls) == 2:
                entered.set()
                release.wait(timeout=2)
            return [[minute.isoformat(), 100, 101, 99, 100, 5]
                    for minute in minutes]
        bridge = IsolatedStreamRecovery(KEY, fetch, min_request_spacing=0.001)
        tick = {"feeds": {KEY: {"ltpc": {
            "ltp": 105, "ltt": str(int(now.timestamp() * 1000))}}}}
        self.assertTrue(bridge.on_message(tick))
        original_join = bridge.worker.join
        try:
            with patch.object(bridge.worker, "join", side_effect=lambda timeout: entered.wait(1)):
                passed, reason = controlled_gap_acceptance(bridge)
            self.assertFalse(passed)
            self.assertEqual(reason, "historical recovery not verified")
            history, _ = bridge.candles.manager.recovery_snapshot(KEY)
            self.assertEqual(len(history), 2)
        finally:
            release.set()
            original_join(timeout=3)

    def test_second_broker_fetch_failure_is_inconclusive_and_cleans_anchors(self):
        now = datetime.now(IST).replace(second=0, microsecond=0)
        minutes = [now - timedelta(minutes=n) for n in (3, 2, 1)]
        if minutes[0].date() != now.date():
            self.skipTest("IST day boundary")
        calls = []
        def fetch(key):
            calls.append(key)
            if len(calls) == 2:
                raise RuntimeError("broker request failed")
            return [[minute.isoformat(), 100, 101, 99, 100, 5]
                    for minute in minutes]
        bridge = IsolatedStreamRecovery(KEY, fetch, min_request_spacing=0.001)
        tick = {"feeds": {KEY: {"ltpc": {
            "ltp": 105, "ltt": str(int(now.timestamp() * 1000))}}}}
        self.assertTrue(bridge.on_message(tick))
        passed, reason = controlled_gap_acceptance(bridge)
        self.assertFalse(passed)
        self.assertEqual(reason, "historical recovery not verified")
        self.assertEqual(len(calls), 2)
        self.assertEqual(bridge.worker.status()["failed"], 1)
        history, active = bridge.candles.manager.recovery_snapshot(KEY)
        self.assertEqual(history, [])
        self.assertEqual(active, now.replace(tzinfo=None))

    def test_reused_initial_broker_object_cannot_pass(self):
        now = datetime.now(IST).replace(second=0, microsecond=0)
        minutes = [now - timedelta(minutes=n) for n in (3, 2, 1)]
        if minutes[0].date() != now.date():
            self.skipTest("IST day boundary")
        from v2.backend.verified_gap_recovery import validated_completed_rows
        initial = validated_completed_rows(
            [[minute.isoformat(), 100, 101, 99, 100, 5] for minute in minutes], now)
        bridge = IsolatedStreamRecovery(KEY, lambda key: [
            [minute.isoformat(), 100, 101, 99, 100, 5] for minute in minutes],
            min_request_spacing=0.001)
        tick = {"feeds": {KEY: {"ltpc": {
            "ltp": 105, "ltt": str(int(now.timestamp() * 1000))}}}}
        self.assertTrue(bridge.on_message(tick))
        # A pathological validator that returns cached candle objects must
        # not be mistaken for independent broker recovery evidence.
        with patch("isolated_controlled_gap_acceptance.validated_completed_rows",
                   return_value=initial):
            with patch("v2.backend.gap_recovery_worker.validated_completed_rows",
                       return_value=initial):
                passed, reason = controlled_gap_acceptance(bridge)
        self.assertFalse(passed)
        self.assertEqual(reason, "recovery reused initial broker candle instead of fresh fetch")

    def test_prior_worker_activity_blocks_controlled_setup(self):
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
        # Even a completed worker with zero insertions invalidates the
        # cumulative counters as independent acceptance evidence.
        with bridge.worker._lock:
            bridge.worker._stats["completed"] = 1
        passed, reason = controlled_gap_acceptance(bridge)
        self.assertFalse(passed)
        self.assertEqual(reason, "prior recovery activity; controlled setup skipped")
        self.assertEqual(len(calls), 0)
        self.assertEqual(bridge.candles.manager.recovery_snapshot(KEY)[0], [])

    def test_live_minute_advancement_during_fetch_is_inconclusive(self):
        now = datetime.now(IST).replace(second=0, microsecond=0)
        minutes = [now - timedelta(minutes=n) for n in (3, 2, 1)]
        if minutes[0].date() != now.date():
            self.skipTest("IST day boundary")
        bridge = None
        calls = []
        def fetch(key):
            calls.append(key)
            if len(calls) == 2:
                later = now + timedelta(minutes=1)
                tick = {"feeds": {KEY: {"ltpc": {
                    "ltp": 106, "ltt": str(int(later.timestamp() * 1000))}}}}
                self.assertTrue(bridge.on_message(tick))
            return [[minute.isoformat(), 100, 101, 99, 100, 5]
                    for minute in minutes]
        bridge = IsolatedStreamRecovery(KEY, fetch, min_request_spacing=0.001)
        tick = {"feeds": {KEY: {"ltpc": {
            "ltp": 105, "ltt": str(int(now.timestamp() * 1000))}}}}
        self.assertTrue(bridge.on_message(tick))
        passed, reason = controlled_gap_acceptance(bridge)
        self.assertFalse(passed)
        self.assertEqual(reason, "isolated candle integrity check failed")
        history, active = bridge.candles.manager.recovery_snapshot(KEY)
        self.assertEqual(active, (now + timedelta(minutes=1)).replace(tzinfo=None))
        self.assertEqual(len(history), 1)
        self.assertEqual(history[0].timestamp, now.replace(tzinfo=None))
        self.assertEqual(history[0].close, 105)

    def test_no_tick_never_fetches_broker(self):
        calls = []
        bridge = IsolatedStreamRecovery(KEY, lambda key: calls.append(key) or [])
        self.assertFalse(controlled_gap_acceptance(bridge)[0])
        self.assertEqual(calls, [])


if __name__ == "__main__":
    unittest.main()
