"""Offline end-to-end test: websocket-shaped ticks + real worker + real manager.

No network, secrets, orders, or production state. Historical response is mocked.
"""
import threading
import unittest
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from isolated_live_tick_candles import IsolatedTickCandles
from isolated_stream_recovery import IsolatedStreamRecovery
from v2.backend.gap_recovery_worker import GapRecoveryWorker

IST = ZoneInfo("Asia/Kolkata")
KEY = "ISOLATED_STREAM"


def message(minute, price):
    return {"feeds": {KEY: {"ltpc": {
        "ltp": price, "ltt": str(int(minute.timestamp() * 1000))
    }}}}


class LiveTickRecoveryTests(unittest.TestCase):
    def test_gap_detected_from_ticks_and_fetch_runs_off_feed_thread(self):
        now = datetime.now(IST).replace(second=0, microsecond=0)
        first, missing, third = (now - timedelta(minutes=3),
                                 now - timedelta(minutes=2),
                                 now - timedelta(minutes=1))
        if first.date() != now.date():
            self.skipTest("IST day boundary")
        caller_thread = threading.current_thread()
        fetched = threading.Event()
        fetch_threads = []
        def fetch(_):
            fetch_threads.append(threading.current_thread())
            fetched.set()
            return [[missing.isoformat(), 101, 102, 100, 101, 10]]
        bridge = IsolatedStreamRecovery(KEY, fetch, cooldown=0.001,
                                        min_request_spacing=0.001)
        self.assertTrue(bridge.on_message(message(first, 100)))
        self.assertTrue(bridge.on_message(message(third, 103)))
        self.assertEqual(bridge.gap_requests, 1)
        self.assertTrue(fetched.wait(2))
        bridge.worker.join(timeout=5)
        self.assertEqual(bridge.worker.status()["verified_insertions"], 1)
        self.assertIsNot(fetch_threads[0], caller_thread)
        history, active = bridge.candles.manager.recovery_snapshot(KEY)
        self.assertEqual([c.timestamp for c in history],
                         [first.replace(tzinfo=None), missing.replace(tzinfo=None)])
        self.assertEqual(active, third.replace(tzinfo=None))

    def test_stale_and_cross_session_ticks_do_not_schedule(self):
        now = datetime.now(IST).replace(second=0, microsecond=0)
        yesterday = now - timedelta(days=1)
        earlier = yesterday.replace(hour=15, minute=27)
        later = now.replace(hour=9, minute=16)
        called = []
        bridge = IsolatedStreamRecovery(KEY, lambda _: called.append(True) or [])
        self.assertTrue(bridge.on_message(message(earlier, 100)))
        self.assertTrue(bridge.on_message(message(later, 101)))
        self.assertTrue(bridge.on_message(message(earlier, 99)))
        self.assertEqual(bridge.gap_requests, 0)
        self.assertEqual(called, [])

    def test_contiguous_ticks_do_not_schedule_recovery(self):
        now = datetime.now(IST).replace(second=0, microsecond=0)
        a, b = now - timedelta(minutes=2), now - timedelta(minutes=1)
        called = []
        bridge = IsolatedStreamRecovery(KEY, lambda _: called.append(True) or [])
        bridge.on_message(message(a, 100))
        bridge.on_message(message(b, 101))
        self.assertEqual(bridge.gap_requests, 0)
        self.assertEqual(called, [])


    def test_ticks_continue_during_delayed_recovery_and_gap_is_idempotent(self):
        now = datetime.now(IST).replace(second=0, microsecond=0)
        first = now - timedelta(minutes=5)
        missing = now - timedelta(minutes=4)
        third = now - timedelta(minutes=3)
        active = now - timedelta(minutes=2)
        newer = now - timedelta(minutes=1)
        if first.date() != now.date():
            self.skipTest("IST day boundary")
        adapter = IsolatedTickCandles(KEY)
        self.assertTrue(adapter.on_message(message(first, 100)))
        self.assertTrue(adapter.on_message(message(third, 103)))
        self.assertTrue(adapter.on_message(message(active, 104)))
        started = threading.Event()
        release = threading.Event()

        def fetch(_key):
            started.set()
            if not release.wait(3):
                raise TimeoutError("offline fetch barrier")
            return [[missing.isoformat(), 101, 102, 100, 101, 10],
                    [third.isoformat(), 999, 999, 999, 999, 999]]

        worker = GapRecoveryWorker(
            fetch, adapter.manager.recovery_snapshot,
            adapter.manager.merge_recovered,
            cooldown=0.001, max_pending=1, min_request_spacing=0.001)
        try:
            self.assertTrue(worker.request(KEY))
            self.assertTrue(started.wait(2))
            # This update uses the same manager lock as recovery; it must not
            # wait for the historical HTTP fetch to complete.
            feed_finished = threading.Event()
            feeder = threading.Thread(
                target=lambda: (adapter.on_message(message(newer, 105)),
                                feed_finished.set()), daemon=True)
            feeder.start()
            self.assertTrue(feed_finished.wait(1), "feed blocked by historical fetch")
            release.set()
            worker.join(timeout=5)
            stats = worker.status()
            self.assertEqual(stats["failed"], 0)
            self.assertEqual(stats["verified_insertions"], 1)
            history, current = adapter.manager.recovery_snapshot(KEY)
            self.assertEqual(current, newer.replace(tzinfo=None))
            self.assertEqual([c.timestamp for c in history], [
                first.replace(tzinfo=None), missing.replace(tzinfo=None),
                third.replace(tzinfo=None), active.replace(tzinfo=None)])
            self.assertEqual(adapter.manager.current[KEY]["candle"].close, 105)
            # Repeated broker data must not duplicate or overwrite candles.
            recovered = {missing.replace(tzinfo=None): history[1]}
            self.assertEqual(adapter.manager.merge_recovered(
                KEY, recovered, active.replace(tzinfo=None)), 0)
            self.assertEqual(len(adapter.manager.recovery_snapshot(KEY)[0]), 4)
        finally:
            release.set()
            worker.join(timeout=5)


if __name__ == "__main__":
    unittest.main()
