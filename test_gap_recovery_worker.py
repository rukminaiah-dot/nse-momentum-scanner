"""Offline worker scheduling tests, no network and no exchange credentials."""
import threading
import unittest
from unittest.mock import patch
from v2.backend.gap_recovery_worker import GapRecoveryWorker

class WorkerTests(unittest.TestCase):
    def test_join_rejects_invalid_timeouts(self):
        worker = GapRecoveryWorker(lambda key: [], lambda key: ([], None),
                                   lambda *args: 0)
        for timeout in (-1, float("nan"), float("inf"), True, "5"):
            with self.subTest(timeout=repr(timeout)):
                with self.assertRaises(ValueError):
                    worker.join(timeout=timeout)
        worker.join(timeout=None)

    def test_join_uses_single_deadline_across_multiple_threads(self):
        import time
        release = threading.Event()
        entered = threading.Event()
        count_lock = threading.Lock()
        started = [0]
        def fetch(_key):
            with count_lock:
                started[0] += 1
                if started[0] == 2:
                    entered.set()
            release.wait(timeout=3)
            return []
        worker = GapRecoveryWorker(
            fetch, lambda key: ([object()], object()),
            lambda *args: 0, max_pending=2, min_request_spacing=0.001)
        try:
            self.assertTrue(worker.request("A"))
            self.assertTrue(worker.request("B"))
            self.assertTrue(entered.wait(2))
            start = time.monotonic()
            worker.join(timeout=0.1)
            self.assertLess(time.monotonic() - start, 0.18)
            self.assertEqual(worker.status()["pending"], 2)
        finally:
            release.set()
            worker.join(timeout=3)

    def test_rate_limit_and_pending_cap(self):
        entered = threading.Event()
        release = threading.Event()
        def fetch(key):
            entered.set()
            release.wait(timeout=3)
            return []
        worker = GapRecoveryWorker(fetch, lambda key: ([object()], object()),
                                   lambda *args: 0, cooldown=120, max_pending=1)
        try:
            self.assertTrue(worker.request("A"))
            self.assertTrue(entered.wait(2))
            self.assertFalse(worker.request("A"))
            self.assertFalse(worker.request("B"))
            stats = worker.status()
            self.assertEqual(stats["requested"], 1)
            self.assertEqual(stats["rejected_pending"], 2)
            self.assertEqual(stats["pending"], 1)
        finally:
            release.set()
            worker.join(timeout=5)

    def test_missing_snapshot_is_skipped_without_api_request(self):
        called = []
        worker = GapRecoveryWorker(lambda key: called.append(key),
                                   lambda key: ([], None), lambda *args: 0)
        self.assertTrue(worker.request("A"))
        worker.join(timeout=5)
        self.assertEqual(called, [])
        self.assertEqual(worker.status()["skipped"], 1)
        self.assertEqual(worker.status()["completed"], 0)
        self.assertEqual(worker.status()["pending"], 0)

    def test_invalid_limits_fail_closed(self):
        with self.assertRaises(ValueError):
            GapRecoveryWorker(None, None, None, min_request_spacing=0)
        with self.assertRaises(ValueError):
            GapRecoveryWorker(None, None, None, max_pending=0)
        with self.assertRaises(ValueError):
            GapRecoveryWorker(None, None, None, cooldown=0)

    def test_nonfinite_rate_limits_fail_closed(self):
        for invalid in (float("nan"), float("inf"), float("-inf")):
            with self.subTest(value=str(invalid)):
                with self.assertRaises(ValueError):
                    GapRecoveryWorker(None, None, None, cooldown=invalid)
                with self.assertRaises(ValueError):
                    GapRecoveryWorker(None, None, None, min_request_spacing=invalid)
        for invalid in (True, 1.5):
            with self.subTest(queue_cap=invalid):
                with self.assertRaises(ValueError):
                    GapRecoveryWorker(None, None, None, max_pending=invalid)

    def test_failure_releases_pending_slot(self):
        finished = threading.Event()
        def fetch(key):
            finished.set()
            raise RuntimeError("offline")
        worker = GapRecoveryWorker(fetch, lambda key: ([object()], object()),
                                   lambda *args: 0, max_pending=1)
        self.assertTrue(worker.request("A"))
        self.assertTrue(finished.wait(2))
        # A different instrument should be admitted after the failed worker
        # has released the slot; avoid racing thread finalization.
        import time
        for _ in range(100):
            with worker._lock:
                if not worker._pending:
                    break
            time.sleep(0.01)
        self.assertTrue(worker.request("B"))
        worker.join(timeout=5)
        self.assertEqual(worker.status()["failed"], 2)
        self.assertEqual(worker.status()["pending"], 0)

    def test_malformed_upstox_response_fails_without_merge(self):
        """Malformed broker rows must not mutate completed candles."""
        from datetime import datetime, timedelta
        from zoneinfo import ZoneInfo
        now = datetime.now(ZoneInfo("Asia/Kolkata"))
        active = (now - timedelta(minutes=1)).replace(second=0, microsecond=0, tzinfo=None)
        if active.date() != now.date():
            self.skipTest("IST session boundary")
        merged = []
        worker = GapRecoveryWorker(
            lambda key: [["invalid-timestamp", 100, 103, 99, 102, 10]],
            lambda key: ([object()], active),
            lambda *args: merged.append(args), max_pending=1)
        self.assertTrue(worker.request("STOCK"))
        worker.join(timeout=5)
        stats = worker.status()
        self.assertEqual(stats["failed"], 1)
        self.assertEqual(stats["completed"], 0)
        self.assertEqual(stats["verified_insertions"], 0)
        self.assertEqual(stats["pending"], 0)
        self.assertEqual(merged, [])

    def test_empty_upstox_response_inserts_nothing(self):
        """A valid empty response is not permission to synthesize bars."""
        from datetime import datetime, timedelta
        from zoneinfo import ZoneInfo
        now = datetime.now(ZoneInfo("Asia/Kolkata"))
        active = (now - timedelta(minutes=1)).replace(second=0, microsecond=0, tzinfo=None)
        if active.date() != now.date():
            self.skipTest("IST session boundary")
        merged = []
        def merge(key, recovered, minute):
            merged.append(recovered)
            return 0
        worker = GapRecoveryWorker(
            lambda key: [], lambda key: ([object()], active), merge)
        self.assertTrue(worker.request("STOCK"))
        worker.join(timeout=5)
        stats = worker.status()
        self.assertEqual(stats["failed"], 0)
        self.assertEqual(stats["completed"], 1)
        self.assertEqual(stats["verified_insertions"], 0)
        self.assertEqual(merged, [{}])

    def test_invalid_ohlcv_response_fails_without_merge(self):
        """Reject contradictory OHLC prices before touching live history."""
        from datetime import datetime, timedelta
        from zoneinfo import ZoneInfo
        now = datetime.now(ZoneInfo("Asia/Kolkata"))
        minute = (now - timedelta(minutes=2)).replace(second=0, microsecond=0)
        if minute.date() != now.date():
            self.skipTest("IST session boundary")
        merged = []
        worker = GapRecoveryWorker(
            lambda key: [[minute.isoformat(), 100, 99, 98, 105, 10]],
            lambda key: ([object()], minute.replace(tzinfo=None) + timedelta(minutes=1)),
            lambda *args: merged.append(args) or 0)
        self.assertTrue(worker.request("STOCK"))
        worker.join(timeout=5)
        self.assertEqual(merged, [])
        self.assertEqual(worker.status()["failed"], 1)
        self.assertEqual(worker.status()["verified_insertions"], 0)
        self.assertEqual(worker.status()["pending"], 0)

    def test_broker_exception_fails_without_merge(self):
        """An Upstox network/API exception must release the worker slot."""
        from datetime import datetime, timedelta
        from zoneinfo import ZoneInfo
        now = datetime.now(ZoneInfo("Asia/Kolkata"))
        active = (now - timedelta(minutes=1)).replace(second=0, microsecond=0, tzinfo=None)
        if active.date() != now.date():
            self.skipTest("IST session boundary")
        merged = []
        def fetch(_):
            raise ConnectionError("simulated broker outage")
        worker = GapRecoveryWorker(
            fetch, lambda key: ([object()], active),
            lambda *args: merged.append(args) or 0)
        self.assertTrue(worker.request("STOCK"))
        worker.join(timeout=5)
        self.assertEqual(merged, [])
        self.assertEqual(worker.status()["failed"], 1)
        self.assertEqual(worker.status()["completed"], 0)
        self.assertEqual(worker.status()["pending"], 0)


    def test_concurrent_feed_update_preserved_during_recovery(self):
        """Feed wins races: delayed recovery must not overwrite a live candle."""
        from datetime import datetime, timedelta
        from zoneinfo import ZoneInfo
        from v2.backend.verified_gap_recovery import merge_verified_missing
        from v2.backend.candles import Candle
        now = datetime.now(ZoneInfo("Asia/Kolkata"))
        base = (now - timedelta(minutes=4)).replace(
            second=0, microsecond=0, tzinfo=None)
        if base.date() != now.date():
            self.skipTest("IST midnight boundary")
        active = base + timedelta(minutes=3)
        state_lock = threading.Lock()
        def candle(minute, price):
            c = Candle(price, 10)
            c.open = c.high = c.low = c.close = price
            c.timestamp = minute
            return c
        first = candle(base, 100)
        live = candle(base + timedelta(minutes=1), 101)
        broker_row = [(base + timedelta(minutes=1)).replace(
            tzinfo=ZoneInfo("Asia/Kolkata")).isoformat(), 99, 99, 99, 99, 10]
        history = [first]
        fetch_started = threading.Event()
        release_fetch = threading.Event()
        def snapshot(_):
            with state_lock:
                return list(history), active
        def fetch(_):
            fetch_started.set()
            if not release_fetch.wait(3):
                raise TimeoutError("test fetch barrier")
            return [broker_row]
        def merge(_, recovered, expected_active):
            nonlocal history
            with state_lock:
                if expected_active != active:
                    return 0
                history, inserted = merge_verified_missing(
                    history, recovered, active_minute=active)
                return len(inserted)
        worker = GapRecoveryWorker(
            fetch, snapshot, merge, cooldown=120,
            max_pending=1, min_request_spacing=0.001)
        try:
            self.assertTrue(worker.request("STOCK"))
            self.assertTrue(fetch_started.wait(2))
            with state_lock:
                history.append(live)
            release_fetch.set()
            worker.join(timeout=5)
            with state_lock:
                self.assertEqual(len(history), 2)
                self.assertIs(history[1], live)
            self.assertEqual(worker.status()["verified_insertions"], 0)
            self.assertEqual(worker.status()["failed"], 0)
            self.assertEqual(worker.status()["pending"], 0)
        finally:
            release_fetch.set()
            worker.join(timeout=5)

if __name__ == "__main__":
    unittest.main()
