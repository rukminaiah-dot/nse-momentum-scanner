"""Paper replay should not invent trades or use future volume."""
import unittest
from datetime import datetime, timedelta
from v2.backend.experimental_15m_replay import replay_symbol


class TestPaperReplay(unittest.TestCase):
    def test_no_verified_volume_no_trades(self):
        start = datetime(2026, 10, 19, 9, 15)
        bars = []
        for i in range(75):
            stamp = start + timedelta(days=i // 25, minutes=15 * (i % 25))
            bars.append({"timestamp": stamp, "open": 100, "high": 101,
                         "low": 99, "close": 100, "volume": 100})
        result = replay_symbol("TEST", bars, cost_pct=0.1)
        self.assertEqual(result["mode"], "PAPER")
        self.assertEqual(result["trades"], [])
        self.assertIsNone(result["summary"]["0.3"]["average_net_pct"])


if __name__ == "__main__":
    unittest.main()
