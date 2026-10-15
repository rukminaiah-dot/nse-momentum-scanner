"""Offline tests for regular-session timestamp validation."""
import unittest
from datetime import datetime
from zoneinfo import ZoneInfo

from v2.backend.session_guard import regular_session_minute, session_tick_action

IST = ZoneInfo("Asia/Kolkata")


def epoch_ms(year, month, day, hour, minute, second=0):
    return int(datetime(year, month, day, hour, minute, second, tzinfo=IST).timestamp() * 1000)


class RegularSessionMinuteTests(unittest.TestCase):
    def test_open_inclusive(self):
        self.assertEqual(regular_session_minute(epoch_ms(2026, 10, 15, 9, 15)),
                         datetime(2026, 10, 15, 9, 15))

    def test_last_regular_minute(self):
        self.assertEqual(regular_session_minute(epoch_ms(2026, 10, 15, 15, 29, 59)),
                         datetime(2026, 10, 15, 15, 29))

    def test_close_exclusive(self):
        for hour, minute in [(9, 14), (15, 30), (15, 50), (15, 55)]:
            with self.subTest(hour=hour, minute=minute):
                self.assertIsNone(regular_session_minute(
                    epoch_ms(2026, 10, 15, hour, minute)))

    def test_close_boundary_finalizes_last_minute_without_new_bar(self):
        active = datetime(2026, 10, 15, 15, 29)
        self.assertEqual(session_tick_action(
            epoch_ms(2026, 10, 15, 15, 30), active), "FINALIZE_LAST_MINUTE")
        self.assertEqual(session_tick_action(
            epoch_ms(2026, 10, 15, 15, 55), active), "FINALIZE_LAST_MINUTE")
        self.assertEqual(session_tick_action(
            epoch_ms(2026, 10, 15, 15, 30), None), "REJECT")

    def test_regular_tick_still_updates(self):
        self.assertEqual(session_tick_action(
            epoch_ms(2026, 10, 15, 15, 29)), "UPDATE")

    def test_close_boundary_does_not_finalize_older_bar(self):
        self.assertEqual(session_tick_action(
            epoch_ms(2026, 10, 15, 15, 30),
            datetime(2026, 10, 15, 15, 28)), "REJECT")

    def test_weekend_rejected(self):
        self.assertIsNone(regular_session_minute(epoch_ms(2026, 10, 17, 10, 0)))

    def test_bad_timestamp_rejected(self):
        for value in (None, "bad", float("inf"), 10**30):
            with self.subTest(value=value):
                self.assertIsNone(regular_session_minute(value))


if __name__ == "__main__":
    unittest.main()
