"""Pure verified-session schedule tests; illustrative dates only."""
import unittest
from datetime import date, datetime, time
from zoneinfo import ZoneInfo

from v2.backend.session_guard import verified_session_minute

IST = ZoneInfo("Asia/Kolkata")


def ms(y, m, d, h, minute):
    return int(datetime(y, m, d, h, minute, tzinfo=IST).timestamp() * 1000)


class VerifiedSessionScheduleTests(unittest.TestCase):
    def test_missing_date_fails_closed(self):
        self.assertIsNone(verified_session_minute(ms(2026, 10, 15, 10, 0), {}))

    def test_regular_session_boundaries(self):
        schedule = {date(2026, 10, 15): (time(9, 15), time(15, 30))}
        self.assertEqual(verified_session_minute(ms(2026, 10, 15, 9, 15), schedule),
                         datetime(2026, 10, 15, 9, 15))
        self.assertIsNone(verified_session_minute(ms(2026, 10, 15, 15, 30), schedule))

    def test_weekend_special_session_explicitly_allowed(self):
        schedule = {date(2026, 10, 17): (time(18, 0), time(19, 0))}
        self.assertEqual(verified_session_minute(ms(2026, 10, 17, 18, 10), schedule),
                         datetime(2026, 10, 17, 18, 10))

    def test_early_close(self):
        schedule = {date(2026, 10, 15): (time(9, 15), time(13, 0))}
        self.assertIsNone(verified_session_minute(ms(2026, 10, 15, 13, 0), schedule))

    def test_malformed_schedule_fails_closed(self):
        for schedule in (None, [], {date(2026, 10, 15): (time(15), time(9))},
                         {date(2026, 10, 15): ("09:15", "15:30")}):
            with self.subTest(schedule=schedule):
                self.assertIsNone(verified_session_minute(
                    ms(2026, 10, 15, 10, 0), schedule))


if __name__ == "__main__":
    unittest.main()
