"""Offline smoke tests for isolated verified candle recovery; no network or broker."""
import unittest
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from v2.backend.verified_gap_recovery import validated_completed_rows, merge_verified_missing
from v2.backend.gap_recovery_worker import GapRecoveryWorker

IST = ZoneInfo("Asia/Kolkata")


def row(minute, close=101):
    return [minute.replace(tzinfo=IST).isoformat(), 100, 102, 99, close, 10]


class VerifiedRecoverySmokeTests(unittest.TestCase):
    def setUp(self):
        self.t0 = datetime(2026, 10, 16, 9, 52)
        self.t1 = self.t0 + timedelta(minutes=1)
        self.now = datetime(2026, 10, 16, 9, 55, tzinfo=IST)

    def test_validates_completed_rows(self):
        result = validated_completed_rows([row(self.t0), row(self.t1)], self.now)
        self.assertEqual(set(result), {self.t0, self.t1})

    def test_rejects_duplicate_minute(self):
        with self.assertRaises(ValueError):
            validated_completed_rows([row(self.t0), row(self.t0)], self.now)

    def test_rejects_active_minute(self):
        result = validated_completed_rows([row(self.t0), row(datetime(2026, 10, 16, 9, 55))], self.now)
        self.assertEqual(set(result), {self.t0})

    def test_merge_is_idempotent_and_does_not_overwrite(self):
        existing = validated_completed_rows([row(self.t0)], self.now)[self.t0]
        recovered = validated_completed_rows([row(self.t0, 100), row(self.t1)], self.now)
        merged, added = merge_verified_missing([existing], recovered, active_minute=self.t1 + timedelta(minutes=1))
        self.assertEqual(added, [self.t1])
        self.assertIs(merged[0], existing)
        repeated, added_again = merge_verified_missing(merged, recovered, active_minute=self.t1 + timedelta(minutes=1))
        self.assertEqual(added_again, [])
        self.assertEqual(len(repeated), 2)

    def test_worker_recovers_only_verified_missing_minute(self):
        existing = validated_completed_rows([row(self.t0)], self.now)[self.t0]
        state = [existing]
        active = self.t1 + timedelta(minutes=1)
        def snapshot(_):
            return list(state), active
        def merge(_, recovered, boundary):
            nonlocal state
            state, added = merge_verified_missing(state, recovered, active_minute=boundary)
            return len(added)
        worker = GapRecoveryWorker(lambda _: [row(self.t1)], snapshot, merge, min_request_spacing=0.001)
        self.assertTrue(worker.request("OFFLINE_TEST"))
        worker.join(timeout=5)
        self.assertEqual(worker.status()["failed"], 0)
        self.assertEqual(worker.status()["verified_insertions"], 1)
        self.assertEqual(len(state), 2)


if __name__ == "__main__":
    unittest.main()
