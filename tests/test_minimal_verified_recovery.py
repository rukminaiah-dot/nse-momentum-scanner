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


    def test_rejects_invalid_ohlcv_and_timezone(self):
        invalid = row(self.t0)
        invalid[2] = 98  # high below open
        with self.assertRaises(ValueError):
            validated_completed_rows([invalid], self.now)
        naive = row(self.t0)
        naive[0] = self.t0.isoformat()
        with self.assertRaises(ValueError):
            validated_completed_rows([naive], self.now)

    def test_worker_failure_does_not_modify_history(self):
        existing = validated_completed_rows([row(self.t0)], self.now)[self.t0]
        state = [existing]
        def broken_fetch(_):
            raise RuntimeError("simulated broker outage")
        worker = GapRecoveryWorker(
            broken_fetch, lambda _: (list(state), self.t1 + timedelta(minutes=1)),
            lambda *_: self.fail("merge must not run after broker failure"),
            min_request_spacing=0.001)
        self.assertTrue(worker.request("OFFLINE_FAILURE"))
        worker.join(timeout=5)
        self.assertEqual(worker.status()["failed"], 1)
        self.assertEqual(worker.status()["pending"], 0)
        self.assertEqual(worker.status()["verified_insertions"], 0)
        self.assertEqual(state, [existing])

    def test_duplicate_request_rejected_while_pending(self):
        import threading
        started = threading.Event()
        release = threading.Event()
        def blocked_fetch(_):
            started.set()
            if not release.wait(5):
                raise TimeoutError("test worker was not released")
            return [row(self.t1)]
        existing = validated_completed_rows([row(self.t0)], self.now)[self.t0]
        state = [existing]
        def merge(_, recovered, active):
            nonlocal state
            state, added = merge_verified_missing(state, recovered, active_minute=active)
            return len(added)
        worker = GapRecoveryWorker(
            blocked_fetch, lambda _: (list(state), self.t1 + timedelta(minutes=1)),
            merge, min_request_spacing=0.001)
        try:
            self.assertTrue(worker.request("SAME_KEY"))
            self.assertTrue(started.wait(5))
            self.assertFalse(worker.request("SAME_KEY"))
        finally:
            release.set()
            worker.join(timeout=5)
        self.assertEqual(worker.status()["rejected_pending"], 1)
        self.assertEqual(worker.status()["verified_insertions"], 1)

    def test_cooldown_rejects_immediate_repeat(self):
        existing = validated_completed_rows([row(self.t0)], self.now)[self.t0]
        worker = GapRecoveryWorker(
            lambda _: [row(self.t1)],
            lambda _: ([existing], self.t1 + timedelta(minutes=1)),
            lambda *_: 0, cooldown=120, min_request_spacing=0.001)
        self.assertTrue(worker.request("COOLDOWN_KEY"))
        worker.join(timeout=5)
        self.assertFalse(worker.request("COOLDOWN_KEY"))
        self.assertEqual(worker.status()["rejected_cooldown"], 1)


    def test_filters_previous_day_and_off_session(self):
        yesterday = self.t0 - timedelta(days=1)
        before_open = self.t0.replace(hour=9, minute=14)
        after_close = self.t0.replace(hour=15, minute=30)
        recovered = validated_completed_rows(
            [row(yesterday), row(before_open), row(after_close), row(self.t0)],
            self.now)
        self.assertEqual(set(recovered), {self.t0})

    def test_rejects_non_finite_and_negative_volume(self):
        for invalid_value in (float("nan"), float("inf"), -1):
            with self.subTest(value=invalid_value):
                invalid = row(self.t0)
                invalid[5] = invalid_value
                with self.assertRaises(ValueError):
                    validated_completed_rows([invalid], self.now)

    def test_merge_rejects_active_or_other_day_and_respects_limit(self):
        earlier = self.t0 - timedelta(minutes=1)
        recovered = validated_completed_rows(
            [row(earlier), row(self.t0), row(self.t1)], self.now)
        active = self.t1
        merged, added = merge_verified_missing(
            [], recovered, active_minute=active, limit=1)
        self.assertEqual([c.timestamp for c in merged], [self.t0])
        self.assertEqual(added, [self.t0])
        self.assertNotIn(active, added)
        with self.assertRaises(ValueError):
            merge_verified_missing([], recovered, active_minute=active, limit=0)


    def test_worker_skips_without_snapshot_history(self):
        fetch_calls = []
        worker = GapRecoveryWorker(
            lambda key: fetch_calls.append(key) or [],
            lambda _: ([], self.t1),
            lambda *_: self.fail("merge must not run without history"),
            min_request_spacing=0.001)
        self.assertTrue(worker.request("EMPTY_HISTORY"))
        worker.join(timeout=5)
        self.assertEqual(fetch_calls, [])
        self.assertEqual(worker.status()["skipped"], 1)
        self.assertEqual(worker.status()["pending"], 0)

    def test_worker_rejects_invalid_broker_rows_before_merge(self):
        existing = validated_completed_rows([row(self.t0)], self.now)[self.t0]
        invalid = row(self.t1)
        invalid[4] = float("nan")
        worker = GapRecoveryWorker(
            lambda _: [invalid],
            lambda _: ([existing], self.t1 + timedelta(minutes=1)),
            lambda *_: self.fail("invalid broker data must never be merged"),
            min_request_spacing=0.001)
        self.assertTrue(worker.request("INVALID_BROKER_DATA"))
        worker.join(timeout=5)
        self.assertEqual(worker.status()["failed"], 1)
        self.assertEqual(worker.status()["verified_insertions"], 0)


    def test_merge_rejects_timestamp_mismatch(self):
        recovered = validated_completed_rows([row(self.t0)], self.now)
        candle = recovered[self.t0]
        candle.timestamp = self.t1
        with self.assertRaises(ValueError):
            merge_verified_missing([], recovered, active_minute=self.t1 + timedelta(minutes=1))

    def test_worker_enforces_global_pending_limit(self):
        import threading
        started = threading.Event()
        release = threading.Event()
        existing = validated_completed_rows([row(self.t0)], self.now)[self.t0]
        def blocked_fetch(_):
            started.set()
            if not release.wait(5):
                raise TimeoutError("test worker was not released")
            return [row(self.t1)]
        worker = GapRecoveryWorker(
            blocked_fetch,
            lambda _: ([existing], self.t1 + timedelta(minutes=1)),
            lambda *_: 0, max_pending=1, min_request_spacing=0.001)
        try:
            self.assertTrue(worker.request("FIRST"))
            self.assertTrue(started.wait(5))
            self.assertFalse(worker.request("SECOND"))
        finally:
            release.set()
            worker.join(timeout=5)
        self.assertEqual(worker.status()["rejected_pending"], 1)
        self.assertEqual(worker.status()["pending"], 0)


    def test_thread_start_failure_releases_slot(self):
        from unittest.mock import patch
        worker = GapRecoveryWorker(
            lambda _: self.fail("broker fetch must not run"),
            lambda _: self.fail("snapshot must not run"),
            lambda *_: self.fail("merge must not run"),
            max_pending=1, min_request_spacing=0.001)
        with patch("v2.backend.gap_recovery_worker.threading.Thread.start",
                   side_effect=RuntimeError("simulated thread startup failure")):
            self.assertFalse(worker.request("START_FAILURE"))
        status = worker.status()
        self.assertEqual(status["pending"], 0)
        self.assertEqual(status["requested"], 0)
        self.assertEqual(status["failed"], 1)
        self.assertEqual(status["rejected_cooldown"], 0)

    def test_invalid_worker_limits_fail_closed(self):
        for kwargs in ({"max_pending": 0}, {"max_pending": True},
                       {"cooldown": 0}, {"min_request_spacing": 0}):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                GapRecoveryWorker(lambda _: [], lambda _: ([], None),
                                  lambda *_: 0, **kwargs)


if __name__ == "__main__":
    unittest.main()
