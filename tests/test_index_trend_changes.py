import unittest
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from v2.backend.index_trend_changes import assess_index_shift

IST = ZoneInfo("Asia/Kolkata")


def make_rows(start, direction, count=6):
    rows = []
    for i in range(count):
        stamp = start + timedelta(minutes=i)
        if direction == "BEARISH":
            rows.append((stamp, 100 - i, 101 - i, 102 - i, -0.2))
        else:
            rows.append((stamp, 100 + i, 99 + i, 98 + i, 0.2))
    return rows


class IndexTrendShiftTests(unittest.TestCase):
    def test_early_watch_after_recent_opposite_trend(self):
        start = datetime(2026, 10, 21, 10, 0, tzinfo=IST)
        old = make_rows(start, "BEARISH", 4)
        # Price/momentum turn up while EMA9 remains below EMA20.
        turn = [
            (start + timedelta(minutes=4), 98.0, 97.5, 98.5, 0.2),
            (start + timedelta(minutes=5), 98.5, 98.0, 98.4, 0.2),
        ]
        result = assess_index_shift(old + turn, now=start + timedelta(minutes=6))
        self.assertEqual(result["data_status"], "LIVE_FRESH")
        self.assertEqual(result["event"], "SHIFT_WATCH")
        self.assertEqual(result["direction"], "BULLISH")

    def test_confirmed_shift_requires_three_aligned_rising_closes(self):
        start = datetime(2026, 10, 21, 10, 0, tzinfo=IST)
        old = make_rows(start, "BEARISH", 4)
        shifted = [
            (start + timedelta(minutes=4), 97.0, 97.5, 98.5, 0.2),
            (start + timedelta(minutes=5), 97.5, 97.8, 98.1, 0.3),
            (start + timedelta(minutes=6), 98.0, 98.1, 98.0, 0.4),
        ]
        result = assess_index_shift(old + shifted, now=start + timedelta(minutes=7))
        self.assertEqual(result["event"], "CONFIRMED_SHIFT")
        self.assertEqual(result["direction"], "BULLISH")

    def test_stale_data_never_reports_live_status(self):
        start = datetime(2026, 10, 21, 10, 0, tzinfo=IST)
        rows = make_rows(start, "BULLISH", 6)
        result = assess_index_shift(rows, now=start + timedelta(minutes=10))
        self.assertEqual(result["data_status"], "STALE")
        self.assertTrue(result["reason"].startswith("Historical/stale data only."))

    def test_after_close_is_historical_not_live(self):
        start = datetime(2026, 10, 21, 15, 20, tzinfo=IST)
        rows = make_rows(start, "BULLISH", 6)
        result = assess_index_shift(rows, now=datetime(2026, 10, 21, 16, 0, tzinfo=IST))
        self.assertEqual(result["data_status"], "HISTORICAL")


if __name__ == "__main__":
    unittest.main()
