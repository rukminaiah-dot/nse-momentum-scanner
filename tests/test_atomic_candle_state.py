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
        self.assertIs(history[0], original)
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


if __name__ == '__main__':
    unittest.main()
