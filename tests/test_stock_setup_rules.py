from datetime import datetime, timedelta
import unittest

from v2.backend.stock_setup_rules import (
    SetupConfig, evaluate_stock_setup, verified_previous_day_levels,
    opening_range_levels, wait_stock_setup,
)


def bar(stamp, open_, high, low, close, volume=200):
    return {"timestamp": stamp, "open": open_, "high": high, "low": low,
            "close": close, "volume": volume}


def slot_history(current, volume=100):
    rows = []
    day = current.date() - timedelta(days=1)
    while len(rows) < 20:
        rows.append([datetime.combine(day, current.time()).isoformat(), 1, 1, 1, 1, volume])
        day -= timedelta(days=1)
    return rows


def breakout_bars(stamp, direction="LONG"):
    """Six-bar compression near a level followed by a strong breakout bar."""
    bars = []
    for i in range(6):
        candle_time = stamp - timedelta(minutes=30 - i * 5)
        if i < 3:
            bars.append(bar(candle_time, 99.0, 101.0, 98.0, 100.0, 1000))
        else:
            bars.append(bar(candle_time, 99.8, 100.2, 99.4, 99.95, 500))
    if direction == "LONG":
        bars.append(bar(stamp, 99.9, 101.3, 99.8, 101.1, 200))
    else:
        bars.append(bar(stamp, 100.1, 100.2, 98.7, 98.9, 200))
    return bars


class StockSetupRuleTests(unittest.TestCase):
    def setUp(self):
        self.stamp = datetime(2026, 10, 21, 10, 0)
        self.config = SetupConfig()

    def test_trigger_requires_completed_strong_candle_and_verified_rvol(self):
        bars = breakout_bars(self.stamp)
        result = evaluate_stock_setup(
            "TEST", bars, slot_history(self.stamp), {"pdh": 100},
            now=self.stamp + timedelta(minutes=5), config=self.config,
        )
        self.assertEqual(result["status"], "TRIGGERED")
        self.assertEqual(result["direction"], "LONG")
        self.assertEqual(result["relative_volume_status"], "VERIFIED_SAME_SLOT_20_SESSIONS")
        self.assertEqual(result["entry_reference"], None)
        self.assertFalse(result["order_execution_enabled"])

    def test_strong_breakout_without_preceding_compression_does_not_trigger(self):
        strong = bar(self.stamp, 99.9, 101.3, 99.8, 101.1)
        result = evaluate_stock_setup(
            "TEST", [strong], slot_history(self.stamp), {"pdh": 100},
            now=self.stamp + timedelta(minutes=5),
        )
        self.assertNotEqual(result["status"], "TRIGGERED")
        self.assertTrue(any("compression before the breakout" in reason
                            for reason in result["reasons"]))

    def test_wick_only_and_missing_volume_history_do_not_trigger(self):
        wick = bar(self.stamp, 99.9, 101.3, 99.8, 100.1)
        result = evaluate_stock_setup("TEST", [wick], slot_history(self.stamp), {"pdh": 100},
                                      now=self.stamp + timedelta(minutes=5))
        self.assertNotEqual(result["status"], "TRIGGERED")
        strong_bars = breakout_bars(self.stamp)
        missing = evaluate_stock_setup("TEST", strong_bars, [], {"pdh": 100},
                                       now=self.stamp + timedelta(minutes=5))
        self.assertEqual(missing["relative_volume_status"], "UNAVAILABLE")
        self.assertNotEqual(missing["status"], "TRIGGERED")

    def test_body_and_close_location_must_both_meet_threshold(self):
        body_too_small = bar(self.stamp, 100.0, 101.4, 99.0, 100.2)
        edge_too_weak = bar(self.stamp, 99.5, 101.5, 99.5, 100.9)
        for candidate in (body_too_small, edge_too_weak):
            bars = breakout_bars(self.stamp)[:-1] + [candidate]
            result = evaluate_stock_setup(
                "TEST", bars, slot_history(self.stamp), {"pdh": 100},
                now=self.stamp + timedelta(minutes=5))
            with self.subTest(candidate=candidate):
                self.assertNotEqual(result["status"], "TRIGGERED")

    def test_short_trigger_is_inverse_and_does_not_require_ema_alignment(self):
        bars = breakout_bars(self.stamp, "SHORT")
        result = evaluate_stock_setup("TEST", bars, slot_history(self.stamp), {"pdl": 100},
                                      now=self.stamp + timedelta(minutes=5), ema9=101, ema20=100)
        self.assertEqual(result["status"], "TRIGGERED")
        self.assertEqual(result["direction"], "SHORT")

    def test_compression_near_resistance_is_watch_with_configurable_thresholds(self):
        bars = []
        for i in range(6):
            stamp = self.stamp - timedelta(minutes=25 - i * 5)
            if i < 3:
                bars.append(bar(stamp, 99.0, 101.0, 98.0, 100.0, 1000))
            else:
                bars.append(bar(stamp, 99.8, 100.2, 99.4, 99.95, 500))
        config = SetupConfig(level_approach_pct=0.2, compression_range_ratio=0.9,
                             compression_volume_ratio=0.9)
        result = evaluate_stock_setup("TEST", bars, [], {"pdh": 100},
                                      now=bars[-1]["timestamp"] + timedelta(minutes=5),
                                      config=config)
        self.assertEqual(result["status"], "WATCH")
        self.assertEqual(result["direction"], "LONG")
        self.assertEqual(result["relative_volume_status"], "UNAVAILABLE")

    def test_next_completed_candle_confirmation_adds_cost_adjusted_plan(self):
        trigger_bars = breakout_bars(self.stamp)
        trigger = evaluate_stock_setup("TEST", trigger_bars, slot_history(self.stamp), {"pdh": 100},
                                       now=self.stamp + timedelta(minutes=5))
        second_stamp = self.stamp + timedelta(minutes=5)
        second = bar(second_stamp, 101.05, 101.5, 100.9, 101.3, 180)
        confirmed = evaluate_stock_setup("TEST", trigger_bars + [second], slot_history(self.stamp),
                                         {"pdh": 100}, now=second_stamp + timedelta(minutes=5),
                                         previous_state=trigger)
        self.assertEqual(confirmed["status"], "CONFIRMED")
        self.assertIsNotNone(confirmed["entry_reference"])
        self.assertIsNotNone(confirmed["stop_invalidation"])
        self.assertIn(confirmed["trade_plan"]["selected_target_percent"], (1, 2))
        self.assertEqual(confirmed["trade_plan"]["slippage"], "UNAVAILABLE")

    def test_blocked_cost_adjusted_targets_do_not_produce_confirmed_entry(self):
        trigger_bars = breakout_bars(self.stamp)
        trigger = evaluate_stock_setup("TEST", trigger_bars, slot_history(self.stamp),
                                       {"pdh": 100}, now=self.stamp + timedelta(minutes=5))
        second_stamp = self.stamp + timedelta(minutes=5)
        second = bar(second_stamp, 101.05, 101.5, 100.9, 101.3, 180)
        result = evaluate_stock_setup(
            "TEST", trigger_bars + [second], slot_history(self.stamp),
            {"pdh": 100, "orh": 101.4}, now=second_stamp + timedelta(minutes=5),
            previous_state=trigger)
        self.assertEqual(result["status"], "INVALID")
        self.assertIsNone(result["entry_reference"])

    def test_close_back_through_level_invalidates(self):
        trigger = {"status": "TRIGGERED", "direction": "LONG", "verified_level": 100,
                   "trigger_candle_time": self.stamp.isoformat(), "setup_id": "once"}
        second_stamp = self.stamp + timedelta(minutes=5)
        failed = bar(second_stamp, 100.2, 100.4, 99.7, 99.9)
        result = evaluate_stock_setup("TEST", [failed], slot_history(self.stamp), {"pdh": 100},
                                      now=second_stamp + timedelta(minutes=5), previous_state=trigger)
        self.assertEqual(result["status"], "INVALID")

    def test_prior_session_confirmation_is_not_carried_forward(self):
        prior = {"status": "CONFIRMED", "direction": "LONG", "verified_level": 100,
                 "trigger_candle_time": "2026-10-20T15:20:00", "setup_id": "old",
                 "entry_reference": 101, "stop_invalidation": 99,
                 "trade_plan": {"reward_to_risk": 2}}
        latest = bar(self.stamp, 99.8, 100.0, 99.5, 99.9)
        result = evaluate_stock_setup("TEST", [latest], [], {"pdh": 100},
                                      now=self.stamp + timedelta(minutes=5),
                                      previous_state=prior)
        self.assertNotEqual(result["status"], "CONFIRMED")

    def test_ema_context_does_not_block_strong_breakout(self):
        bars = breakout_bars(self.stamp)
        result = evaluate_stock_setup("TEST", bars, slot_history(self.stamp), {"pdh": 100},
                                      now=self.stamp + timedelta(minutes=5), ema9=99,
                                      ema20=100)
        self.assertEqual(result["status"], "TRIGGERED")
        self.assertEqual((result["ema9"], result["ema20"]), (99, 100))

    def test_previous_day_levels_require_complete_verified_session(self):
        session = datetime(2026, 10, 20, 9, 15)
        rows = []
        for minute in range(375):
            stamp = session + timedelta(minutes=minute)
            rows.append([stamp.isoformat(), 100, 110 if minute == 100 else 105,
                         90 if minute == 200 else 95, 100, 1000])
        levels = verified_previous_day_levels(rows, datetime(2026, 10, 21).date())
        self.assertEqual(levels["pdh"], 110)
        self.assertEqual(levels["pdl"], 90)
        self.assertIsNone(verified_previous_day_levels(rows[:-1], datetime(2026, 10, 21).date()))

    def test_opening_range_requires_first_three_completed_bars(self):
        session = datetime(2026, 10, 21, 9, 15)
        bars = [bar(session + timedelta(minutes=5 * i), 100 + i, 102 + i,
                    99 + i, 101 + i, 100) for i in range(3)]
        levels = opening_range_levels(bars, session_date=session.date())
        self.assertEqual(levels["orh"], 104)
        self.assertEqual(levels["orl"], 99)
        self.assertIsNone(opening_range_levels(bars[1:], session_date=session.date()))

    def test_wait_state_exposes_verified_levels_and_latest_completed_candle(self):
        session = datetime(2026, 10, 21, 9, 15)
        bars = [
            bar(session, 99, 101, 98, 100),
            bar(session + timedelta(minutes=5), 100, 102, 99, 101),
            bar(session + timedelta(minutes=10), 101, 103, 100, 102),
            bar(session + timedelta(minutes=15), 102, 103, 101, 102),
        ]

        result = evaluate_stock_setup("TEST", bars, [], {},
                                      now=session + timedelta(minutes=20))

        self.assertEqual(result["status"], "WAIT")
        self.assertEqual(result["last_completed_candle_time"],
                         (session + timedelta(minutes=15)).isoformat())
        self.assertEqual(result["last_completed_close"], 102.0)
        references = {level["name"]: level for level in result["verified_levels"]}
        self.assertEqual(references["OPENING_RANGE_HIGH"]["value"], 103.0)
        self.assertEqual(references["OPENING_RANGE_LOW"]["value"], 98.0)

    def test_upstream_data_blocker_is_a_read_only_wait_with_specific_reason(self):
        result = wait_stock_setup(
            "TEST", "WAIT: 1-minute candle continuity is MISSING_MINUTE",
            last_observed_minute_candle_time="2026-10-21T10:00:00",
        )

        self.assertEqual(result["status"], "WAIT")
        self.assertEqual(result["reasons"], ["WAIT: 1-minute candle continuity is MISSING_MINUTE"])
        self.assertEqual(result["last_observed_minute_candle_time"], "2026-10-21T10:00:00")
        self.assertEqual(result["relative_volume_status"], "UNAVAILABLE")
        self.assertIsNone(result["entry_reference"])
        self.assertFalse(result["order_execution_enabled"])


if __name__ == "__main__":
    unittest.main()
