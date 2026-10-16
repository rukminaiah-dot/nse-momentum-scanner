"""Offline tests for experimental candle-manager atomic recovery API."""
import unittest
from datetime import datetime
from zoneinfo import ZoneInfo
from v2.backend.candle_manager import CandleManager
from v2.backend.candles import Candle

IST = ZoneInfo("Asia/Kolkata")


def millis(hour, minute):
    return int(datetime(2026, 10, 16, hour, minute, tzinfo=IST).timestamp() * 1000)


def recovered(hour, minute, price=100):
    candle = Candle(price, 1)
    candle.timestamp = datetime(2026, 10, 16, hour, minute)
    return candle


class AtomicCandleStateTests(unittest.TestCase):
    def test_no_active_minute_means_no_insert(self):
        manager = CandleManager()
        candle = recovered(9, 15)
        self.assertEqual(manager.insert_missing_completed('X', {candle.timestamp: candle}), 0)
        self.assertEqual(manager.snapshot('X'), ([], None))

    def test_insert_only_missing_completed_minutes(self):
        manager = CandleManager()
        manager.update('X', 100, millis(9, 15))
        manager.update('X', 101, millis(9, 17))
        existing, active = manager.snapshot('X')
        self.assertEqual(active, datetime(2026, 10, 16, 9, 17))
        original = existing[0]
        missing = recovered(9, 16)
        future = recovered(9, 17)
        batch = {original.timestamp: recovered(9, 15, 500),
                 missing.timestamp: missing, future.timestamp: future}
        self.assertEqual(manager.insert_missing_completed('X', batch), 1)
        history, _ = manager.snapshot('X')
        self.assertEqual([c.timestamp for c in history],
                         [datetime(2026, 10, 16, 9, 15), datetime(2026, 10, 16, 9, 16)])
        self.assertIsNot(history[0], original)
        self.assertEqual(history[0].timestamp, original.timestamp)
        self.assertEqual(history[0].close, original.close)
        self.assertEqual(manager.insert_missing_completed('X', batch), 0)

    def test_rechecks_active_boundary(self):
        manager = CandleManager()
        manager.update('X', 100, millis(9, 15))
        manager.update('X', 101, millis(9, 16))
        _, stale_boundary = manager.snapshot('X')
        manager.update('X', 102, millis(9, 17))
        self.assertEqual(stale_boundary, datetime(2026, 10, 16, 9, 16))
        gap = recovered(9, 16)
        # The live update already closed 09:16, so never overwrite it.
        self.assertEqual(manager.insert_missing_completed('X', {gap.timestamp: gap}), 0)
        history, _ = manager.snapshot('X')
        self.assertEqual(len(history), 2)
        self.assertEqual(history[-1].close, 101)


    def test_invalid_batch_is_atomic(self):
        manager = CandleManager()
        manager.update('X', 100, millis(9, 15))
        manager.update('X', 101, millis(9, 18))
        before, _ = manager.snapshot('X')
        valid = recovered(9, 16)
        invalid = recovered(9, 17)
        invalid.timestamp = datetime(2026, 10, 16, 9, 19)
        with self.assertRaises(ValueError):
            manager.insert_missing_completed('X', {
                datetime(2026, 10, 16, 9, 16): valid,
                datetime(2026, 10, 16, 9, 17): invalid,
            })
        after, _ = manager.snapshot('X')
        self.assertEqual([c.timestamp for c in before],
                         [c.timestamp for c in after])


    def test_recovery_insert_does_not_emit_candle_close(self):
        from unittest.mock import patch
        manager = CandleManager()
        manager.update('X', 100, millis(9, 15))
        manager.update('X', 101, millis(9, 17))
        missing = recovered(9, 16)
        with patch.object(manager, 'update',
                          side_effect=AssertionError('recovery must not call update')):
            self.assertEqual(manager.insert_missing_completed(
                'X', {missing.timestamp: missing}), 1)
        history, active = manager.snapshot('X')
        self.assertEqual(active, datetime(2026, 10, 16, 9, 17))
        self.assertEqual(len(history), 2)


    def test_history_limit_counts_only_retained_insertions(self):
        manager = CandleManager()
        manager.update('X', 100, millis(9, 15))
        manager.update('X', 101, millis(9, 19))
        old = recovered(9, 16)
        recent = recovered(9, 18)
        count = manager.insert_missing_completed(
            'X', {old.timestamp: old, recent.timestamp: recent}, limit=1)
        history, _ = manager.snapshot('X')
        self.assertEqual([c.timestamp for c in history],
                         [datetime(2026, 10, 16, 9, 18)])
        self.assertEqual(count, 1)


    def test_recovery_does_not_modify_active_candle(self):
        manager = CandleManager()
        manager.update('X', 100, millis(9, 15))
        manager.update('X', 101, millis(9, 17))
        active_before = manager.current['X']['candle']
        close_before = active_before.close
        missing = recovered(9, 16)
        manager.insert_missing_completed('X', {missing.timestamp: missing})
        self.assertIs(manager.current['X']['candle'], active_before)
        self.assertEqual(manager.current['X']['candle'].close, close_before)

    def test_recovery_rejects_invalid_limit_without_mutation(self):
        manager = CandleManager()
        manager.update('X', 100, millis(9, 15))
        manager.update('X', 101, millis(9, 17))
        before, _ = manager.snapshot('X')
        missing = recovered(9, 16)
        for limit in (0, True, -1):
            with self.subTest(limit=limit), self.assertRaises(ValueError):
                manager.insert_missing_completed(
                    'X', {missing.timestamp: missing}, limit=limit)
        after, _ = manager.snapshot('X')
        self.assertEqual([c.timestamp for c in before],
                         [c.timestamp for c in after])


    def test_duplicate_recovery_does_not_replace_history_list(self):
        manager = CandleManager()
        manager.update('X', 100, millis(9, 15))
        manager.update('X', 101, millis(9, 17))
        original_history = manager.completed['X']
        duplicate = recovered(9, 15, 999)
        self.assertEqual(manager.insert_missing_completed(
            'X', {duplicate.timestamp: duplicate}), 0)
        self.assertIs(manager.completed['X'], original_history)


    def test_live_update_and_recovery_are_serialized(self):
        import threading
        manager = CandleManager()
        manager.update('X', 100, millis(9, 15))
        manager.update('X', 101, millis(9, 17))
        ready = threading.Barrier(3)
        errors = []
        missing = recovered(9, 16)

        def live():
            try:
                ready.wait(timeout=5)
                manager.update('X', 102, millis(9, 18))
            except Exception as exc:
                errors.append(exc)

        def repair():
            try:
                ready.wait(timeout=5)
                manager.insert_missing_completed('X', {missing.timestamp: missing})
            except Exception as exc:
                errors.append(exc)

        threads = [threading.Thread(target=live), threading.Thread(target=repair)]
        for thread in threads:
            thread.start()
        ready.wait(timeout=5)
        for thread in threads:
            thread.join(timeout=5)
        self.assertFalse(errors)
        self.assertTrue(all(not thread.is_alive() for thread in threads))
        history, active = manager.snapshot('X')
        self.assertEqual(active, datetime(2026, 10, 16, 9, 18))
        self.assertEqual([c.timestamp for c in history],
                         [datetime(2026, 10, 16, 9, 15),
                          datetime(2026, 10, 16, 9, 16),
                          datetime(2026, 10, 16, 9, 17)])


    def test_delayed_tick_does_not_roll_active_minute_back(self):
        manager = CandleManager()
        manager.update('X', 100, millis(9, 15))
        manager.update('X', 101, millis(9, 17))
        history_before, active_before = manager.snapshot('X')
        self.assertIsNone(manager.update('X', 999, millis(9, 16)))
        history_after, active_after = manager.snapshot('X')
        self.assertEqual(active_after, active_before)
        self.assertEqual([c.timestamp for c in history_after],
                         [c.timestamp for c in history_before])
        self.assertEqual(manager.current['X']['candle'].close, 101)

    def test_recovery_ignores_other_session_date(self):
        manager = CandleManager()
        manager.update('X', 100, millis(9, 15))
        manager.update('X', 101, millis(9, 17))
        previous = recovered(9, 16)
        previous.timestamp = datetime(2026, 10, 15, 9, 16)
        self.assertEqual(manager.insert_missing_completed(
            'X', {previous.timestamp: previous}), 0)
        history, active = manager.snapshot('X')
        self.assertEqual(len(history), 1)
        self.assertEqual(active, datetime(2026, 10, 16, 9, 17))


    def test_preload_copies_history_and_refuses_live_overwrite(self):
        manager = CandleManager()
        original = [recovered(9, 15)]
        manager.preload_completed('X', original)
        original.append(recovered(9, 16))
        history, active = manager.snapshot('X')
        self.assertEqual(len(history), 1)
        self.assertIsNone(active)
        manager.update('X', 101, millis(9, 17))
        with self.assertRaises(RuntimeError):
            manager.preload_completed('X', [recovered(9, 16)])
        history_after, _ = manager.snapshot('X')
        self.assertEqual(len(history_after), 1)


    def test_update_returns_close_event_only_on_live_rollover(self):
        manager = CandleManager()
        self.assertIsNone(manager.update('X', 100, millis(9, 15)))
        self.assertIsNone(manager.update('X', 101, millis(9, 15)))
        closed = manager.update('X', 102, millis(9, 17))
        self.assertIsNotNone(closed)
        self.assertEqual(closed.timestamp, datetime(2026, 10, 16, 9, 15))
        missing = recovered(9, 16)
        self.assertEqual(manager.insert_missing_completed(
            'X', {missing.timestamp: missing}), 1)
        self.assertIsNone(manager.update('X', 103, millis(9, 17)))
        self.assertIsNone(manager.update('X', 999, millis(9, 16)))


    def test_recovery_history_growth_is_not_live_close_event(self):
        manager = CandleManager()
        manager.update('X', 100, millis(9, 15))
        manager.update('X', 101, millis(9, 17))
        before = len(manager.snapshot('X')[0])
        missing = recovered(9, 16)
        self.assertEqual(manager.insert_missing_completed(
            'X', {missing.timestamp: missing}), 1)
        # A history-length comparison would falsely interpret this as a close.
        self.assertGreater(len(manager.snapshot('X')[0]), before)
        self.assertIsNone(manager.update('X', 102, millis(9, 17)))


    def test_recovery_waits_for_live_rollover_and_preserves_closed_bar(self):
        import threading
        manager = CandleManager()
        manager.update('X', 100, millis(9, 15))
        manager.update('X', 101, millis(9, 17))
        attempted = threading.Event()
        finished = threading.Event()
        errors = []
        recovered_bar = recovered(9, 17, 999)

        def repair():
            try:
                attempted.set()
                manager.insert_missing_completed(
                    'X', {recovered_bar.timestamp: recovered_bar})
            except Exception as exc:
                errors.append(exc)
            finally:
                finished.set()

        # Force the rollover to win the manager lock. The recovery worker
        # must re-read the new active boundary rather than overwrite 09:17.
        with manager._state_lock:
            thread = threading.Thread(target=repair)
            thread.start()
            self.assertTrue(attempted.wait(timeout=5))
            self.assertFalse(finished.is_set())
            closed = manager.update('X', 102, millis(9, 18))
            self.assertEqual(closed.timestamp, datetime(2026, 10, 16, 9, 17))
        thread.join(timeout=5)
        self.assertFalse(thread.is_alive())
        self.assertFalse(errors)
        history, active = manager.snapshot('X')
        self.assertEqual(active, datetime(2026, 10, 16, 9, 18))
        self.assertEqual([c.timestamp for c in history],
                         [datetime(2026, 10, 16, 9, 15),
                          datetime(2026, 10, 16, 9, 17)])
        self.assertEqual(history[-1].close, 101)


    def test_recovery_wins_lock_before_rollover_without_duplicate_close(self):
        import threading
        manager = CandleManager()
        manager.update('X', 100, millis(9, 15))
        manager.update('X', 101, millis(9, 17))
        ready = threading.Event()
        finished = threading.Event()
        errors = []
        gap = recovered(9, 16, 99)

        def live():
            try:
                ready.set()
                manager.update('X', 102, millis(9, 18))
            except Exception as exc:
                errors.append(exc)
            finally:
                finished.set()

        # Force recovery to commit while the live rollover is blocked.
        # After release, the rollover must append only the real 09:17 bar.
        with manager._state_lock:
            thread = threading.Thread(target=live)
            thread.start()
            self.assertTrue(ready.wait(timeout=5))
            self.assertFalse(finished.is_set())
            self.assertEqual(manager.insert_missing_completed(
                'X', {gap.timestamp: gap}), 1)
        thread.join(timeout=5)
        self.assertFalse(thread.is_alive())
        self.assertFalse(errors)
        history, active = manager.snapshot('X')
        self.assertEqual(active, datetime(2026, 10, 16, 9, 18))
        self.assertEqual([c.timestamp for c in history],
                         [datetime(2026, 10, 16, 9, 15),
                          datetime(2026, 10, 16, 9, 16),
                          datetime(2026, 10, 16, 9, 17)])
        self.assertEqual(history[-1].close, 101)


    def test_recovered_candle_is_not_aliased_to_caller(self):
        manager = CandleManager()
        manager.update('X', 100, millis(9, 15))
        manager.update('X', 101, millis(9, 17))
        gap = recovered(9, 16, 99)
        self.assertEqual(manager.insert_missing_completed(
            'X', {gap.timestamp: gap}), 1)
        gap.update(999, 50)
        history, _ = manager.snapshot('X')
        repaired = next(c for c in history
                        if c.timestamp == datetime(2026, 10, 16, 9, 16))
        self.assertIsNot(repaired, gap)
        self.assertEqual(repaired.close, 99)
        self.assertEqual(repaired.volume, 1)


    def test_snapshot_mutation_cannot_change_manager_history(self):
        manager = CandleManager()
        manager.update('X', 100, millis(9, 15))
        manager.update('X', 101, millis(9, 17))
        snapshot, _ = manager.snapshot('X')
        snapshot[0].update(999, 10)
        snapshot[0].timestamp = datetime(2026, 10, 16, 9, 14)
        stored, _ = manager.snapshot('X')
        self.assertEqual(stored[0].close, 100)
        self.assertEqual(stored[0].volume, 0)
        self.assertEqual(stored[0].timestamp, datetime(2026, 10, 16, 9, 15))

    def test_preload_copies_candle_objects_not_just_list(self):
        manager = CandleManager()
        source = recovered(9, 15, 100)
        manager.preload_completed('X', [source])
        source.update(999, 10)
        stored, _ = manager.snapshot('X')
        self.assertEqual(stored[0].close, 100)
        self.assertEqual(stored[0].volume, 1)


    def test_recovery_cannot_bridge_session_boundary(self):
        manager = CandleManager()
        manager.update('X', 100, millis(9, 15))
        manager.update('X', 101, millis(9, 17))
        # A later session starts a new active candle, but prior completed
        # history may remain available for EMA warmup.
        next_day = int(datetime(2026, 10, 19, 9, 15, tzinfo=IST).timestamp() * 1000)
        manager.update('X', 102, next_day)
        prior_session_gap = recovered(9, 16, 99)
        self.assertEqual(manager.insert_missing_completed(
            'X', {prior_session_gap.timestamp: prior_session_gap}), 0)
        history, active = manager.snapshot('X')
        self.assertEqual(active, datetime(2026, 10, 19, 9, 15))
        self.assertNotIn(prior_session_gap.timestamp,
                         [c.timestamp for c in history])


    def test_snapshot_stays_consistent_during_concurrent_updates(self):
        import threading
        manager = CandleManager()
        manager.update('X', 100, millis(9, 15))
        started = threading.Event()
        errors = []

        def writer():
            try:
                started.set()
                for minute in range(16, 46):
                    manager.update('X', minute, millis(9, minute))
            except Exception as exc:
                errors.append(exc)

        thread = threading.Thread(target=writer)
        thread.start()
        self.assertTrue(started.wait(timeout=5))
        while thread.is_alive():
            history, active = manager.snapshot('X')
            timestamps = [c.timestamp for c in history]
            self.assertEqual(timestamps, sorted(timestamps))
            self.assertEqual(len(timestamps), len(set(timestamps)))
            if timestamps:
                self.assertLess(timestamps[-1], active)
        thread.join(timeout=5)
        self.assertFalse(thread.is_alive())
        self.assertFalse(errors)
        history, active = manager.snapshot('X')
        self.assertEqual(len(history), 30)
        self.assertEqual(active, datetime(2026, 10, 16, 9, 45))


    def test_independent_instruments_do_not_share_recovery_state(self):
        manager = CandleManager()
        for key in ("A", "B"):
            manager.update(key, 100, millis(9, 15))
            manager.update(key, 101, millis(9, 17))
        gap = recovered(9, 16, 99)
        self.assertEqual(manager.insert_missing_completed(
            "A", {gap.timestamp: gap}), 1)
        a_history, a_active = manager.snapshot("A")
        b_history, b_active = manager.snapshot("B")
        self.assertEqual(a_active, b_active)
        self.assertEqual([c.timestamp.minute for c in a_history], [15, 16])
        self.assertEqual([c.timestamp.minute for c in b_history], [15])
        # Mutating a detached A snapshot must not affect either instrument.
        a_history[0].update(999)
        self.assertEqual(manager.snapshot("A")[0][0].close, 100)
        self.assertEqual(manager.snapshot("B")[0][0].close, 100)


if __name__ == '__main__':
    unittest.main()
