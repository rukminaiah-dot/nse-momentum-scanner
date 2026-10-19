"""Offline concurrency gate for Fix 10: websocket-style feed must never wait for recovery.

No broker access, secrets, market data, orders or production state are used.
Run: python -m unittest -v tests.test_recovery_nonblocking_gate
"""
import threading
import time
import unittest
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from v2.backend.gap_recovery_worker import GapRecoveryWorker

IST = ZoneInfo("Asia/Kolkata")


class NonblockingRecoveryGate(unittest.TestCase):
    def test_feed_progresses_while_history_request_is_blocked(self):
        started = threading.Event()
        release = threading.Event()
        state_lock = threading.Lock()
        now = datetime.now(IST).replace(second=0, microsecond=0, tzinfo=None)
        prior = now - timedelta(minutes=2)
        active = now - timedelta(minutes=1)
        state = {"active": active, "history": [object()], "feed_updates": 0, "merges": 0}

        def snapshot(_key):
            with state_lock:
                return list(state["history"]), state["active"]

        def fetch_rows(_key):
            started.set()
            if not release.wait(3):
                raise TimeoutError("isolated historical API simulation timed out")
            return []

        def merge(_key, recovered, original_active):
            with state_lock:
                # A delayed response must not revert an active feed minute.
                self.assertGreaterEqual(state["active"], original_active)
                self.assertEqual(recovered, {})
                state["merges"] += 1
                return 0

        worker = GapRecoveryWorker(
            fetch_rows, snapshot, merge, cooldown=1,
            max_pending=1, min_request_spacing=0.01,
        )
        try:
            self.assertTrue(worker.request("ISOLATED_TEST"))
            self.assertTrue(started.wait(2), "worker never reached history request")
            # This models a live websocket callback, on the calling thread.
            began = time.monotonic()
            with state_lock:
                state["active"] = now
                state["feed_updates"] += 1
            elapsed = time.monotonic() - began
            self.assertLess(elapsed, 0.25, "feed blocked by pending recovery")
            self.assertEqual(state["feed_updates"], 1)
            self.assertEqual(worker.status()["pending"], 1)
        finally:
            release.set()
            worker.join(timeout=4)
        self.assertEqual(worker.status()["pending"], 0)
        self.assertEqual(worker.status()["failed"], 0)
        self.assertEqual(worker.status()["completed"], 1)
        self.assertEqual(state["merges"], 1)

    def test_pending_limit_does_not_block_feed_thread(self):
        started = threading.Event()
        release = threading.Event()

        def fetch_rows(_key):
            started.set()
            if not release.wait(3):
                raise TimeoutError("isolated request timed out")
            return []

        worker = GapRecoveryWorker(
            fetch_rows,
            lambda _key: ([object()], datetime.now(IST).replace(tzinfo=None)),
            lambda _key, _rows, _active: 0,
            cooldown=1, max_pending=1, min_request_spacing=0.01,
        )
        try:
            self.assertTrue(worker.request("FIRST"))
            self.assertTrue(started.wait(2))
            began = time.monotonic()
            self.assertFalse(worker.request("SECOND"))
            self.assertLess(time.monotonic() - began, 0.25)
            self.assertEqual(worker.status()["rejected_pending"], 1)
        finally:
            release.set()
            worker.join(timeout=4)
        self.assertEqual(worker.status()["pending"], 0)


if __name__ == "__main__":
    unittest.main()
