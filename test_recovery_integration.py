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

if __name__ == "__main__":
    unittest.main()
