"""Offline tests for optional bounded candle history."""
import unittest
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from v2.backend.candle_manager import CandleManager
from v2.backend.candles import Candle
from v2.backend.indicators import ema, momentum
from v2.backend.signal_engine import generate_signal


def bars(count):
    start = datetime(2026, 10, 16, 9, 15)
    result = []
    for i in range(count):
        c = Candle(100 + i, 0)
        c.timestamp = start + timedelta(minutes=i)
        result.append(c)
    return result


class RetentionTests(unittest.TestCase):
    def test_rejects_invalid_limits(self):
        for value in (0, -1, True, 1.5, "60"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                CandleManager(max_completed_per_symbol=value)

    def test_default_unbounded_and_preload_cap(self):
        full = CandleManager()
        full.preload_completed("X", bars(5))
        self.assertEqual(len(full.snapshot("X")[0]), 5)
        capped = CandleManager(max_completed_per_symbol=2)
        capped.preload_completed("X", bars(5))
        self.assertEqual([c.timestamp.minute for c in capped.snapshot("X")[0]], [18, 19])

    def test_live_rollover_caps_completed_not_active(self):
        manager = CandleManager(max_completed_per_symbol=2)
        start = datetime(2026, 10, 16, 9, 15, tzinfo=ZoneInfo("Asia/Kolkata"))
        for i in range(5):
            manager.update("X", 100 + i, int((start + timedelta(minutes=i)).timestamp() * 1000))
        completed, active = manager.snapshot("X")
        self.assertEqual([c.timestamp.minute for c in completed], [17, 18])
        self.assertEqual(active.minute, 19)

    def test_old_recovery_cannot_evict_recent_history(self):
        manager = CandleManager(max_completed_per_symbol=2)
        manager.preload_completed("X", bars(5)[3:])
        active_ts = datetime(2026, 10, 16, 9, 20, tzinfo=ZoneInfo("Asia/Kolkata"))
        manager.update("X", 105, int(active_ts.timestamp() * 1000))
        older = bars(1)[0]
        self.assertEqual(manager.insert_missing_completed("X", {older.timestamp: older}), 0)
        self.assertEqual([c.timestamp.minute for c in manager.snapshot("X")[0]], [18, 19])

    def test_retention_preserves_recent_indicator_window(self):
        # Current scanner EMA20/ATR14 and RVOL20 need at least 20 bars.
        manager = CandleManager(max_completed_per_symbol=60)
        manager.preload_completed("X", bars(100))
        completed, _ = manager.snapshot("X")
        self.assertEqual(len(completed), 60)
        self.assertEqual([c.timestamp for c in completed[-20:]],
                         [c.timestamp for c in bars(100)[-20:]])

    def test_ema_seed_changes_with_retention_even_above_period(self):
        # EMA starts from the first value, so a cap above EMA20 is not
        # mathematically equivalent to unbounded history.
        values = [100.0 + i for i in range(80)] + [150.0] * 20
        self.assertNotEqual(ema(values, 20), ema(values[-60:], 20))

    def test_overnight_rollover_preserves_latest_cross_session_history(self):
        manager = CandleManager(max_completed_per_symbol=3)
        friday = datetime(2026, 10, 16, 15, 28, tzinfo=ZoneInfo("Asia/Kolkata"))
        monday = datetime(2026, 10, 19, 9, 15, tzinfo=ZoneInfo("Asia/Kolkata"))
        for i in range(3):
            manager.update("X", 100 + i, int((friday + timedelta(minutes=i)).timestamp() * 1000))
        manager.update("X", 103, int(monday.timestamp() * 1000))
        manager.update("X", 104, int((monday + timedelta(minutes=1)).timestamp() * 1000))
        completed, active = manager.snapshot("X")
        self.assertEqual(len(completed), 3)
        self.assertEqual([c.timestamp for c in completed],
                         [datetime(2026, 10, 16, 15, 29),
                          datetime(2026, 10, 16, 15, 30),
                          datetime(2026, 10, 19, 9, 15)])
        self.assertEqual(active, datetime(2026, 10, 19, 9, 16))
        # Recovery from Friday must not enter Monday's active session.
        old = Candle(99, 0)
        old.timestamp = datetime(2026, 10, 16, 15, 27)
        self.assertEqual(manager.insert_missing_completed("X", {old.timestamp: old}), 0)
        self.assertEqual(len(manager.snapshot("X")[0]), 3)

    def test_ema_drift_decays_with_longer_retention(self):
        # Deterministic synthetic regimes; quantify rather than assume parity.
        regimes = {
            "trend": [100.0 + i * 0.25 for i in range(400)],
            "step": [100.0] * 200 + [140.0] * 200,
            "alternating": [100.0 + (8.0 if i % 2 else -8.0) for i in range(400)],
        }
        for name, values in regimes.items():
            full = ema(values, 20)
            drift_60 = abs(full - ema(values[-60:], 20))
            drift_200 = abs(full - ema(values[-200:], 20))
            with self.subTest(regime=name):
                self.assertLessEqual(drift_200, drift_60 + 1e-10)

    def test_capped_recovery_keeps_newest_missing_minute(self):
        manager = CandleManager(max_completed_per_symbol=3)
        original = bars(6)
        manager.preload_completed("X", [original[0], original[2], original[4]])
        active_ts = datetime(2026, 10, 16, 9, 21, tzinfo=ZoneInfo("Asia/Kolkata"))
        manager.update("X", 106, int(active_ts.timestamp() * 1000))
        recovered = {original[i].timestamp: original[i] for i in (1, 3, 5)}
        inserted = manager.insert_missing_completed("X", recovered)
        completed, _ = manager.snapshot("X")
        self.assertEqual(inserted, 2)
        self.assertEqual([c.timestamp.minute for c in completed], [18, 19, 20])

    def test_stronger_core_filters_reject_marginal_short_ema_drift(self):
        # Tiny 60-bar drifts do not meet the minimum EMA-spread rule.
        history = 400
        scenarios = (
            ("BUY", [150.0] * (history - 60)
             + [100.0 + i * 0.0001 for i in range(60)]),
            ("SELL", [50.0] * (history - 60)
             + [100.0 - i * 0.0001 for i in range(60)]),
        )

        def signal(values):
            return generate_signal(
                values[-1], ema(values, 9), ema(values, 20),
                None, momentum(values), rvol=1.5, market="NEUTRAL",
            )

        for capped_decision, prices in scenarios:
            with self.subTest(capped_decision=capped_decision):
                self.assertEqual(signal(prices), "HOLD")
                self.assertEqual(signal(prices[-60:]), "HOLD")


if __name__ == "__main__":
    unittest.main()
