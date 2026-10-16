"""Offline integration of the real recovery worker and atomic candle manager."""
import unittest
from datetime import datetime
from threading import Event
from unittest.mock import patch
from zoneinfo import ZoneInfo

from v2.backend.candle_manager import CandleManager
from v2.backend.gap_recovery_worker import GapRecoveryWorker

IST = ZoneInfo("Asia/Kolkata")


def ts(hour, minute):
    return int(datetime(2026, 10, 16, hour, minute, tzinfo=IST).timestamp() * 1000)


def row(hour, minute, price):
    return [datetime(2026, 10, 16, hour, minute, tzinfo=IST).isoformat(),
            price, price, price, price, 10]


class WorkerManagerIntegrationTests(unittest.TestCase):
    def setUp(self):
        # Broker validation must not depend on the day CI happens to run.
        clock = patch('v2.backend.gap_recovery_worker.datetime')
        fake_datetime = clock.start()
        fake_datetime.now.return_value = datetime(2026, 10, 16, 10, 0, tzinfo=IST)
        self.addCleanup(clock.stop)

    def test_worker_fills_only_missing_minute_and_is_idempotent(self):
        manager = CandleManager()
        manager.update("X", 100, ts(9, 15))
        manager.update("X", 102, ts(9, 17))
        worker = GapRecoveryWorker(
            lambda key: [row(9, 15, 999), row(9, 16, 101)],
            manager.snapshot, manager.merge_verified_recovery,
            cooldown=0.001, min_request_spacing=0.001)
        self.assertTrue(worker.request("X"))
        worker.join()
        history, active = manager.snapshot("X")
        self.assertEqual([c.timestamp.minute for c in history], [15, 16])
        self.assertEqual([c.close for c in history], [100, 101])
        self.assertEqual(active.minute, 17)
        self.assertEqual(worker.status()["verified_insertions"], 1)
        self.assertTrue(worker.request("X"))
        worker.join()
        self.assertEqual(worker.status()["verified_insertions"], 1)

    def test_delayed_broker_response_cannot_repair_prior_session(self):
        manager = CandleManager()
        manager.update("X", 100, ts(9, 15))
        manager.update("X", 102, ts(9, 17))
        entered, release = Event(), Event()

        def fetch(key):
            entered.set()
            if not release.wait(5):
                raise RuntimeError("test fetch timeout")
            return [row(9, 16, 101)]

        worker = GapRecoveryWorker(
            fetch, manager.snapshot, manager.merge_verified_recovery,
            min_request_spacing=0.001)
        self.assertTrue(worker.request("X"))
        self.assertTrue(entered.wait(5))
        later = int(datetime(2026, 10, 19, 9, 15, tzinfo=IST).timestamp() * 1000)
        manager.update("X", 103, later)
        release.set()
        worker.join()
        history, active = manager.snapshot("X")
        self.assertEqual(active.date(), datetime(2026, 10, 19).date())
        self.assertNotIn(datetime(2026, 10, 16, 9, 16),
                         [c.timestamp for c in history])
        self.assertEqual(worker.status()["verified_insertions"], 0)


if __name__ == "__main__":
    unittest.main()
