"""End-to-end offline worker verification with real candle manager and fake Upstox rows."""
import unittest
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from v2.backend.candle_manager import CandleManager
from v2.backend.gap_recovery_worker import GapRecoveryWorker

IST = ZoneInfo("Asia/Kolkata")

class WorkerIntegrationTests(unittest.TestCase):
    def test_worker_restores_missing_minute_without_overwriting_live_candle(self):
        manager = CandleManager()
        key = "OFFLINE_STOCK"
        now = datetime.now(IST).replace(second=0, microsecond=0)
        first, missing, third, active = (
            now - timedelta(minutes=4), now - timedelta(minutes=3),
            now - timedelta(minutes=2), now - timedelta(minutes=1)
        )
        # Use same-session data; no live exchange or credentials.
        if first.date() != now.date():
            self.skipTest("session boundary")
        def tick(stamp, price):
            manager.update(key, price, int(stamp.timestamp() * 1000), 10)
        tick(first, 100)
        tick(third, 102)
        tick(active, 104)
        def fetch(_):
            return [[missing.isoformat(), 101, 103, 100, 102, 15],
                    [third.isoformat(), 999, 999, 999, 999, 999]]
        worker = GapRecoveryWorker(fetch, manager.recovery_snapshot,
                                   manager.merge_recovered, cooldown=1,
                                   max_pending=1, min_request_spacing=0.01)
        self.assertTrue(worker.request(key))
        worker.join(timeout=5)
        status = worker.status()
        self.assertEqual(status["failed"], 0)
        self.assertEqual(status["verified_insertions"], 1)
        self.assertEqual(status["pending"], 0)
        history, active_minute = manager.recovery_snapshot(key)
        self.assertEqual([c.timestamp for c in history], [
            first.replace(tzinfo=None), missing.replace(tzinfo=None),
            third.replace(tzinfo=None)])
        self.assertEqual(history[-1].close, 102)
        self.assertEqual(active_minute, active.replace(tzinfo=None))


    def test_feed_advances_active_minute_during_delayed_recovery(self):
        """Real CandleManager lock: recovery must not replace newer feed state."""
        import threading
        manager = CandleManager()
        key = "ADVANCING_FEED"
        now = datetime.now(IST).replace(second=0, microsecond=0)
        first = now - timedelta(minutes=5)
        missing = now - timedelta(minutes=4)
        third = now - timedelta(minutes=3)
        active = now - timedelta(minutes=2)
        newer = now - timedelta(minutes=1)
        if first.date() != now.date():
            self.skipTest("session boundary")
        def tick(stamp, price):
            manager.update(key, price, int(stamp.timestamp() * 1000), 10)
        tick(first, 100)
        tick(third, 103)
        tick(active, 104)
        fetch_started = threading.Event()
        release_fetch = threading.Event()
        def fetch(_):
            fetch_started.set()
            if not release_fetch.wait(3):
                raise TimeoutError("test fetch barrier")
            return [[missing.isoformat(), 101, 102, 100, 101, 15],
                    [third.isoformat(), 999, 999, 999, 999, 999]]
        worker = GapRecoveryWorker(
            fetch, manager.recovery_snapshot, manager.merge_recovered,
            cooldown=1, max_pending=1, min_request_spacing=0.01)
        try:
            self.assertTrue(worker.request(key))
            self.assertTrue(fetch_started.wait(2))
            tick(newer, 105)
            release_fetch.set()
            worker.join(timeout=5)
            self.assertEqual(worker.status()["failed"], 0)
            self.assertEqual(worker.status()["pending"], 0)
            self.assertEqual(worker.status()["verified_insertions"], 1)
            history, current_minute = manager.recovery_snapshot(key)
            self.assertEqual(current_minute, newer.replace(tzinfo=None))
            self.assertEqual([c.timestamp for c in history], [
                first.replace(tzinfo=None), missing.replace(tzinfo=None),
                third.replace(tzinfo=None), active.replace(tzinfo=None)])
            self.assertEqual(history[-1].close, 104)
        finally:
            release_fetch.set()
            worker.join(timeout=5)

if __name__ == "__main__":
    unittest.main()
