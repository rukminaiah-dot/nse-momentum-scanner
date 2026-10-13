"""Offline worker scheduling tests, no network and no exchange credentials."""
import threading
import unittest
from unittest.mock import patch
from v2.backend.gap_recovery_worker import GapRecoveryWorker

class WorkerTests(unittest.TestCase):
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
        finally:
            release.set()

    def test_invalid_limits_fail_closed(self):
        with self.assertRaises(ValueError):
            GapRecoveryWorker(None, None, None, max_pending=0)
        with self.assertRaises(ValueError):
            GapRecoveryWorker(None, None, None, cooldown=0)

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

if __name__ == "__main__":
    unittest.main()
