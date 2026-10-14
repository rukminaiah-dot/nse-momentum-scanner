"""Offline regression tests for verified gap recovery (no Upstox credentials)."""
import unittest
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from v2.backend.verified_gap_recovery import validated_completed_rows, merge_verified_missing
from v2.backend.candle_manager import CandleManager

IST = ZoneInfo("Asia/Kolkata")
NOW = datetime(2026, 10, 13, 11, 45, tzinfo=IST)

def row(minute, volume=10):
    return [datetime(2026, 10, 13, 11, minute, tzinfo=IST).isoformat(),
            100, 103, 99, 102, volume]

class GapRecoveryTests(unittest.TestCase):
    def test_idempotent_recovery_normalizes_equal_length_history(self):
        manager = CandleManager(log_closed_candles=False)
        key = "NORMALIZE_TEST"
        for minute in (40, 41, 42):
            stamp = datetime(2026, 10, 13, 11, minute, tzinfo=IST)
            manager.update(key, 100, int(stamp.timestamp() * 1000))
        original, active = manager.recovery_snapshot(key)
        manager.completed[key] = list(reversed(original))
        self.assertEqual(manager.merge_recovered(key, {}, active), 0)
        normalized, still_active = manager.recovery_snapshot(key)
        self.assertEqual([c.timestamp.minute for c in normalized], [40, 41])
        self.assertTrue(all(a is b for a, b in zip(normalized, original)))
        self.assertEqual(still_active, active)

    def test_idempotent_manager_recovery_still_trims_completed_history(self):
        manager = CandleManager(log_closed_candles=False)
        key = "RETENTION_TEST"
        base = datetime(2026, 10, 13, 10, 0, tzinfo=IST)
        for offset in range(75):
            stamp = int((base + timedelta(minutes=offset)).timestamp() * 1000)
            manager.update(key, 100 + offset, stamp)
        before, active = manager.recovery_snapshot(key)
        self.assertEqual(len(before), 74)
        self.assertEqual(manager.merge_recovered(key, {}, active), 0)
        after, still_active = manager.recovery_snapshot(key)
        self.assertEqual(len(after), 60)
        self.assertEqual([c.timestamp for c in after],
                         [c.timestamp for c in before[-60:]])
        self.assertEqual(still_active, active)

    def test_merge_discards_completed_candles_at_or_after_active(self):
        manager = CandleManager(log_closed_candles=False)
        key = "FUTURE_COMPLETED"
        active_stamp = datetime(2026, 10, 13, 11, 43, tzinfo=IST)
        manager.update(key, 105, int(active_stamp.timestamp() * 1000))
        from v2.backend.candles import Candle
        for minute in (41, 43, 44):
            candle = Candle(100, 0)
            candle.timestamp = datetime(2026, 10, 13, 11, minute)
            manager.completed.setdefault(key, []).append(candle)
        _, active = manager.recovery_snapshot(key)
        self.assertEqual(manager.merge_recovered(key, {}, active), 0)
        completed, unchanged = manager.recovery_snapshot(key)
        self.assertEqual([c.timestamp.minute for c in completed], [41])
        self.assertEqual(unchanged, active)
        self.assertEqual(manager.current[key]["candle"].close, 105)

    def test_merge_drops_stale_session_completed_bars(self):
        manager = CandleManager(log_closed_candles=False)
        key = "STALE_HISTORY"
        today = datetime(2026, 10, 14, 9, 15, tzinfo=IST)
        manager.update(key, 105, int(today.timestamp() * 1000))
        old = datetime(2026, 10, 13, 15, 29, tzinfo=IST)
        manager.completed[key] = []
        from v2.backend.candles import Candle
        stale = Candle(100, 0)
        stale.timestamp = old.replace(tzinfo=None)
        manager.completed[key].append(stale)
        _, active = manager.recovery_snapshot(key)
        self.assertEqual(manager.merge_recovered(key, {}, active), 0)
        self.assertEqual(manager.recovery_snapshot(key)[0], [])
        self.assertEqual(manager.current[key]["candle"].close, 105)

    def test_missing_active_boundary_never_inserts_broker_history(self):
        recovered = validated_completed_rows([row(41)], NOW)
        merged, added = merge_verified_missing([], recovered)
        self.assertEqual(merged, [])
        self.assertEqual(added, [])

    def test_completed_only_and_order(self):
        got = validated_completed_rows([row(44), row(42), row(45)], NOW)
        self.assertEqual([t.minute for t in sorted(got)], [42, 44])

    def test_reject_malformed_top_level_broker_batches(self):
        for malformed in (None, 123, True, {"candles": [row(42)]},
                          "not a candle batch"):
            with self.subTest(malformed=repr(malformed)):
                with self.assertRaisesRegex(ValueError, "invalid Upstox candle batch"):
                    validated_completed_rows(malformed, NOW)

    def test_reject_malformed_broker_row_shapes(self):
        for malformed in (None, 123, True, {"timestamp": "bad"}, "bad"):
            with self.subTest(malformed=repr(malformed)):
                with self.assertRaises(ValueError):
                    validated_completed_rows([malformed], NOW)

    def test_reject_boolean_ohlcv_fields(self):
        for column in range(1, 6):
            for value in (True, False):
                with self.subTest(column=column, value=value):
                    malformed = row(42)
                    malformed[column] = value
                    with self.assertRaisesRegex(ValueError, "boolean OHLCV"):
                        validated_completed_rows([malformed], NOW)

    def test_invalid_broker_batch_cannot_partially_merge(self):
        manager = CandleManager(log_closed_candles=False)
        key = "ATOMIC_BATCH"
        for minute in (40, 43):
            stamp = datetime(2026, 10, 13, 11, minute, tzinfo=IST)
            manager.update(key, 100, int(stamp.timestamp() * 1000), 10)
        original, active = manager.recovery_snapshot(key)
        self.assertEqual([c.timestamp.minute for c in original], [40])
        malformed = row(42)
        malformed[4] = float("nan")
        with self.assertRaises(ValueError):
            verified = validated_completed_rows([row(41), malformed], NOW)
            manager.merge_recovered(key, verified, active)
        after, current = manager.recovery_snapshot(key)
        self.assertEqual(current, active)
        self.assertEqual(len(after), len(original))
        self.assertTrue(all(a is b for a, b in zip(after, original)))
        self.assertEqual(manager.current[key]["candle"].close, 100)

    def test_reject_bad_ohlcv(self):
        for bad in ([row(42, -1)], [row(42), row(42)],
                    [[row(42)[0], 100, 98, 99, 102, 10]],
                    [[row(42)[0], 100, 103, 99, float("nan"), 10]]):
            with self.subTest(bad=bad):
                with self.assertRaises(ValueError):
                    validated_completed_rows(bad, NOW)

    def test_reject_non_datetime_validation_clock(self):
        for invalid in (None, 0, True, "2026-10-13T11:45:00+05:30"):
            with self.subTest(clock=repr(invalid)):
                with self.assertRaisesRegex(ValueError, "current time must be datetime"):
                    validated_completed_rows([row(42)], invalid)

    def test_reject_naive_current_clock(self):
        with self.assertRaises(ValueError):
            validated_completed_rows([row(42)], datetime(2026, 10, 13, 11, 45))

    def test_utc_current_clock_normalizes_to_ist(self):
        from datetime import timezone
        got = validated_completed_rows([row(42)], NOW.astimezone(timezone.utc))
        self.assertEqual([t.minute for t in got], [42])

    def test_accept_utc_broker_timestamp_and_normalize_to_ist(self):
        from datetime import timezone
        stamp = datetime(2026, 10, 13, 11, 42, tzinfo=IST)
        candle_row = row(42)
        candle_row[0] = stamp.astimezone(timezone.utc).isoformat()
        verified = validated_completed_rows([candle_row], NOW)
        self.assertEqual(list(verified), [stamp.replace(tzinfo=None)])
        self.assertEqual(verified[stamp.replace(tzinfo=None)].close, 102)

    def test_reject_non_string_broker_timestamps(self):
        for invalid in (None, 0, True, 1234567890000):
            with self.subTest(timestamp=repr(invalid)):
                malformed = row(42)
                malformed[0] = invalid
                with self.assertRaisesRegex(ValueError, "invalid candle timestamp type"):
                    validated_completed_rows([malformed], NOW)

    def test_reject_naive_timestamp(self):
        with self.assertRaises(ValueError):
            validated_completed_rows([["2026-10-13T11:42:00", 100, 103, 99, 102, 10]], NOW)

    def test_merge_only_missing_and_preserve_live(self):
        existing = validated_completed_rows([row(40), row(42)], NOW)
        recovered = validated_completed_rows([row(40, 500), row(41), row(42, 500), row(44)], NOW)
        merged, added = merge_verified_missing(
            [existing[t] for t in sorted(existing)], recovered,
            active_minute=datetime(2026, 10, 13, 11, 44))
        self.assertEqual([t.minute for t in added], [41])
        self.assertEqual([c.timestamp.minute for c in merged], [40, 41, 42])
        self.assertEqual(merged[0].volume, 10)

    def test_merge_rejects_mismatched_candle_timestamp(self):
        candle = next(iter(validated_completed_rows([row(41)], NOW).values()))
        incorrect_key = datetime(2026, 10, 13, 11, 42)
        with self.assertRaises(ValueError):
            merge_verified_missing([], {incorrect_key: candle},
                active_minute=datetime(2026, 10, 13, 11, 44))

    def test_merge_drops_previous_session(self):
        candle = next(iter(validated_completed_rows([row(41)], NOW).values()))
        prior = datetime(2026, 10, 12, 11, 41)
        candle.timestamp = prior
        merged, added = merge_verified_missing([], {prior: candle},
            active_minute=datetime(2026, 10, 13, 11, 44))
        self.assertEqual(merged, [])
        self.assertEqual(added, [])

    def test_no_synthetic_missing_minutes(self):
        recovered = validated_completed_rows([row(40), row(43)], NOW)
        merged, added = merge_verified_missing(
            [], recovered, active_minute=datetime(2026, 10, 13, 11, 44))
        self.assertEqual([t.minute for t in added], [40, 43])
        self.assertEqual(len(merged), 2)

    def test_prior_session_is_not_recovered(self):
        prior = ["2026-10-12T15:29:00+05:30", 100, 103, 99, 102, 10]
        got = validated_completed_rows([prior, row(42)], NOW)
        self.assertEqual([t.minute for t in got], [42])

    def test_history_limit(self):
        recovered = validated_completed_rows([row(i) for i in range(35, 45)], NOW)
        merged, added = merge_verified_missing(
            [], recovered, active_minute=datetime(2026, 10, 13, 11, 45), limit=6)
        self.assertEqual(len(added), 6)
        self.assertEqual([t.minute for t in added], list(range(39, 45)))
        self.assertEqual([c.timestamp.minute for c in merged], list(range(39, 45)))

    def test_invalid_history_limit(self):
        for limit in (0, -1, True, False, None, 1.5, "60"):
            with self.subTest(limit=limit):
                with self.assertRaisesRegex(ValueError, "invalid history limit"):
                    merge_verified_missing([], {}, limit=limit)

    def test_merge_accepted_after_active_minute_advances(self):
        manager = CandleManager()
        key = "TEST"
        def tick(minute):
            stamp = datetime(2026, 10, 13, 11, minute, tzinfo=IST)
            manager.update(key, 100, int(stamp.timestamp() * 1000), 10)
        tick(40)
        tick(42)
        _, expected_active = manager.recovery_snapshot(key)
        tick(43)
        recovered = validated_completed_rows([row(41)], NOW)
        self.assertEqual(manager.merge_recovered(key, recovered, expected_active), 1)
        self.assertEqual([c.timestamp.minute for c in manager.completed[key]], [40, 41, 42])

    def test_stale_broker_snapshot_never_overwrites_new_live_minute(self):
        manager = CandleManager(log_closed_candles=False)
        key = "ADVANCED_FEED"
        def tick(minute, price):
            stamp = datetime(2026, 10, 13, 11, minute, tzinfo=IST)
            manager.update(key, price, int(stamp.timestamp() * 1000))
        tick(40, 100)
        tick(42, 102)
        _, expected_active = manager.recovery_snapshot(key)
        tick(44, 104)
        recovered = validated_completed_rows([row(41), row(43)], NOW)
        self.assertEqual(manager.merge_recovered(key, recovered, expected_active), 2)
        history, active = manager.recovery_snapshot(key)
        self.assertEqual([c.timestamp.minute for c in history], [40, 41, 42, 43])
        self.assertEqual(active.minute, 44)
        self.assertEqual(manager.current[key]["candle"].close, 104)

    def test_merge_rejects_future_snapshot(self):
        manager = CandleManager()
        key = "TEST"
        stamp = datetime(2026, 10, 13, 11, 42, tzinfo=IST)
        manager.update(key, 100, int(stamp.timestamp() * 1000), 10)
        recovered = validated_completed_rows([row(41)], NOW)
        self.assertEqual(manager.merge_recovered(key, recovered, datetime(2026, 10, 13, 11, 43)), 0)

    def test_previous_session_response_cannot_repopulate_new_day(self):
        manager = CandleManager(log_closed_candles=False)
        key = "STALE_RESPONSE"
        yesterday = datetime(2026, 10, 13, 15, 29, tzinfo=IST)
        manager.update(key, 100, int(yesterday.timestamp() * 1000))
        _, previous_active = manager.recovery_snapshot(key)
        today = datetime(2026, 10, 14, 9, 15, tzinfo=IST)
        manager.update(key, 105, int(today.timestamp() * 1000))
        recovered = validated_completed_rows([row(41)], NOW)
        self.assertEqual(manager.merge_recovered(key, recovered, previous_active), 0)
        history, active = manager.recovery_snapshot(key)
        self.assertEqual(history, [])
        self.assertEqual(active, today.replace(tzinfo=None))
        self.assertEqual(manager.current[key]["candle"].close, 105)

    def test_new_session_rollover_does_not_clear_other_instruments(self):
        manager = CandleManager(log_closed_candles=False)
        previous = datetime(2026, 10, 13, 15, 28, tzinfo=IST)
        following = datetime(2026, 10, 13, 15, 29, tzinfo=IST)
        for key in ("A", "B"):
            manager.update(key, 100, int(previous.timestamp() * 1000))
            manager.update(key, 101, int(following.timestamp() * 1000))
        other_history, other_active = manager.recovery_snapshot("B")
        self.assertEqual(len(other_history), 1)
        today = datetime(2026, 10, 14, 9, 15, tzinfo=IST)
        manager.update("A", 105, int(today.timestamp() * 1000))
        self.assertEqual(manager.recovery_snapshot("A")[0], [])
        preserved, still_active = manager.recovery_snapshot("B")
        self.assertEqual(still_active, other_active)
        self.assertEqual(len(preserved), 1)
        self.assertIs(preserved[0], other_history[0])

    def test_new_trading_day_clears_multiple_prior_completed_bars(self):
        manager = CandleManager(log_closed_candles=False)
        key = "SESSION_BOUNDARY"
        for minute in (27, 28, 29):
            stamp = datetime(2026, 10, 13, 15, minute, tzinfo=IST)
            manager.update(key, 100 + minute, int(stamp.timestamp() * 1000))
        before, _ = manager.recovery_snapshot(key)
        self.assertEqual([c.timestamp.minute for c in before], [27, 28])
        next_day = datetime(2026, 10, 14, 9, 15, tzinfo=IST)
        self.assertIsNone(manager.update(key, 105, int(next_day.timestamp() * 1000)))
        history, active = manager.recovery_snapshot(key)
        self.assertEqual(history, [])
        self.assertEqual(active, next_day.replace(tzinfo=None))
        following = datetime(2026, 10, 14, 9, 16, tzinfo=IST)
        manager.update(key, 106, int(following.timestamp() * 1000))
        history, _ = manager.recovery_snapshot(key)
        self.assertEqual([c.timestamp for c in history],
                         [next_day.replace(tzinfo=None)])

    def test_first_tick_discards_orphaned_completed_history(self):
        manager = CandleManager(log_closed_candles=False)
        key = "REINITIALIZED"
        previous = datetime(2026, 10, 13, 15, 29, tzinfo=IST)
        today = datetime(2026, 10, 14, 9, 15, tzinfo=IST)
        manager.update(key, 100, int(previous.timestamp() * 1000))
        manager.update(key, 101, int((previous + timedelta(minutes=1)).timestamp() * 1000))
        self.assertEqual(len(manager.completed[key]), 1)
        manager.current.pop(key)
        self.assertIsNone(manager.update(key, 105, int(today.timestamp() * 1000)))
        history, active = manager.recovery_snapshot(key)
        self.assertEqual(history, [])
        self.assertEqual(active, today.replace(tzinfo=None))
        self.assertEqual(manager.current[key]["candle"].close, 105)

    def test_cross_session_rollover_returns_no_closed_candle(self):
        manager = CandleManager(log_closed_candles=False)
        key = "NEW_SESSION"
        previous = datetime(2026, 10, 13, 15, 29, tzinfo=IST)
        today = datetime(2026, 10, 14, 9, 15, tzinfo=IST)
        self.assertIsNone(manager.update(key, 100, int(previous.timestamp() * 1000)))
        self.assertIsNone(manager.update(key, 105, int(today.timestamp() * 1000)))
        history, active = manager.recovery_snapshot(key)
        self.assertEqual(history, [])
        self.assertEqual(active, today.replace(tzinfo=None))
        self.assertEqual(manager.current[key]["candle"].close, 105)

    def test_delayed_merge_rejected_across_session_boundary(self):
        manager = CandleManager()
        key = "TEST"
        for day, minute in ((13, 40), (14, 40)):
            stamp = datetime(2026, 10, day, 11, minute, tzinfo=IST)
            manager.update(key, 100, int(stamp.timestamp() * 1000), 10)
        recovered = validated_completed_rows([row(41)], NOW)
        previous_session = datetime(2026, 10, 13, 11, 42)
        self.assertEqual(manager.merge_recovered(key, recovered, previous_session), 0)
        self.assertEqual(manager.completed.get(key, []), [])
        self.assertEqual(manager.current[key]["minute"].date(), datetime(2026, 10, 14).date())

    def test_merge_inserts_gap_without_overwriting_live(self):
        manager = CandleManager()
        key = "TEST"
        for minute in (40, 42):
            stamp = datetime(2026, 10, 13, 11, minute, tzinfo=IST)
            manager.update(key, 100, int(stamp.timestamp() * 1000), 10)
        _, expected_active = manager.recovery_snapshot(key)
        recovered = validated_completed_rows([row(40, 900), row(41)], NOW)
        self.assertEqual(manager.merge_recovered(key, recovered, expected_active), 1)
        self.assertEqual([c.timestamp.minute for c in manager.completed[key]], [40, 41])
        self.assertEqual(manager.completed[key][0].volume, 10)

if __name__ == "__main__":
    unittest.main()
