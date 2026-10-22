"""Volume-baseline safety tests for the paper-only 15-minute experiment."""
import unittest
from datetime import datetime, timedelta
from v2.backend.experimental_15m_volume import verified_15m_same_slot_average


class Test15mVolumeBaseline(unittest.TestCase):
    def setUp(self):
        self.current = {"timestamp": datetime(2026, 10, 21, 10, 0), "volume": 180}
        self.history = []
        day = datetime(2026, 9, 1, 10, 0)
        while len(self.history) < 21:
            if day.weekday() < 5:
                self.history.append({"timestamp": day, "volume": 100})
            day += timedelta(days=1)

    def test_exactly_21_prior_trading_sessions(self):
        self.assertEqual(verified_15m_same_slot_average(self.current, self.history), 100)

    def test_partial_history_blocked(self):
        self.assertIsNone(verified_15m_same_slot_average(self.current, self.history[:20]))

    def test_duplicate_slot_blocked(self):
        self.assertIsNone(verified_15m_same_slot_average(
            self.current, self.history + [self.history[0]]))

    def test_future_data_ignored(self):
        future = {"timestamp": datetime(2026, 10, 22, 10, 0), "volume": 9999}
        self.assertEqual(verified_15m_same_slot_average(
            self.current, self.history + [future]), 100)

    def test_weekend_bar_does_not_count_as_trading_session(self):
        weekend = {"timestamp": datetime(2026, 10, 17, 10, 0), "volume": 100}
        self.assertIsNone(verified_15m_same_slot_average(
            self.current, self.history[:20] + [weekend]))

    def test_wrong_slot_ignored(self):
        self.history[-1]["timestamp"] += timedelta(minutes=15)
        self.assertIsNone(verified_15m_same_slot_average(self.current, self.history))


if __name__ == "__main__":
    unittest.main()
