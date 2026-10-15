"""Offline checks only: no Upstox connection or production state."""
import unittest
from datetime import datetime
from zoneinfo import ZoneInfo

from v2.backend.nonproduction_timestamp_observer import TimestampObserver, observe_ltt

IST = ZoneInfo("Asia/Kolkata")


def millis(hour, minute, second=0):
    return int(datetime(2026, 10, 15, hour, minute, second, tzinfo=IST).timestamp() * 1000)


class ObserverTests(unittest.TestCase):
    def test_post_close_fresh_tick_not_called_valid_session(self):
        record = observe_ltt(millis(15, 58), millis(15, 58, 1))
        self.assertEqual(record["status"], "FRESH")
        self.assertEqual(record["regular_hours_window"], "AFTER_REGULAR_HOURS")
        self.assertEqual(record["session"], "UNKNOWN")

    def test_arrival_skew_and_seconds(self):
        record = observe_ltt(millis(10, 0) // 1000, millis(10, 3))
        self.assertEqual(record["status"], "STALE")
        self.assertEqual(record["arrival_minus_event_ms"], 180000)

    def test_invalid_and_aggregate_redaction(self):
        observer = TimestampObserver()
        self.assertEqual(observer.record(None, millis(10, 0))["status"], "INVALID")
        observer.record(millis(9, 14), millis(9, 14))
        summary = observer.summary()
        self.assertEqual(sum(row["count"] for row in summary), 2)
        self.assertNotIn("event_ist", str(summary))
        self.assertNotIn("instrument_key", str(summary))

    def test_close_boundary(self):
        self.assertEqual(observe_ltt(millis(15, 29), millis(15, 29))["regular_hours_window"],
                         "WITHIN_REGULAR_HOURS")
        self.assertEqual(observe_ltt(millis(15, 30), millis(15, 30))["regular_hours_window"],
                         "AFTER_REGULAR_HOURS")


if __name__ == "__main__":
    unittest.main()
