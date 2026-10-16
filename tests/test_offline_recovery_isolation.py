"""Credential-free recovery isolation test; no scanner, database, or broker imports."""
import unittest
from datetime import datetime
from zoneinfo import ZoneInfo
from unittest.mock import patch

from v2.backend.candle_manager import CandleManager
from v2.backend.gap_recovery_worker import GapRecoveryWorker

IST = ZoneInfo("Asia/Kolkata")


def milliseconds(hour, minute):
    return int(datetime(2026, 10, 16, hour, minute, tzinfo=IST).timestamp() * 1000)


class OfflineRecoveryIsolationTests(unittest.TestCase):
    def test_synthetic_gap_repair_never_emits_live_close(self):
        manager = CandleManager()
        manager.update("SYNTHETIC", 100, milliseconds(9, 15))
        manager.update("SYNTHETIC", 102, milliseconds(9, 17))
        fetches = []

        def synthetic_fetch(key):
            fetches.append(key)
            return [
                [datetime(2026, 10, 16, 9, 15, tzinfo=IST).isoformat(),
                 999, 999, 999, 999, 1],
                [datetime(2026, 10, 16, 9, 16, tzinfo=IST).isoformat(),
                 101, 101, 101, 101, 1],
            ]

        worker = GapRecoveryWorker(
            synthetic_fetch, manager.snapshot, manager.merge_verified_recovery,
            min_request_spacing=0.001,
        )
        try:
            with patch("v2.backend.gap_recovery_worker.datetime") as clock:
                clock.now.return_value = datetime(2026, 10, 16, 10, 0, tzinfo=IST)
                self.assertTrue(worker.request("SYNTHETIC"))
                worker.join(timeout=5)
            history, active = manager.snapshot("SYNTHETIC")
            self.assertEqual(fetches, ["SYNTHETIC"])
            self.assertEqual([bar.timestamp.minute for bar in history], [15, 16])
            self.assertEqual([bar.close for bar in history], [100, 101])
            self.assertEqual(active.minute, 17)
            self.assertEqual(worker.status()["verified_insertions"], 1)
            self.assertIsNone(manager.update("SYNTHETIC", 103, milliseconds(9, 17)))
            worker.close(timeout=5)
            self.assertFalse(worker.request("SYNTHETIC"))
        finally:
            worker.close(timeout=5)


if __name__ == "__main__":
    unittest.main()
