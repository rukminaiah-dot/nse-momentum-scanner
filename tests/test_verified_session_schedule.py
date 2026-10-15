"""Pure verified-session schedule tests; illustrative dates only."""
import unittest
from datetime import date, datetime, time
from zoneinfo import ZoneInfo

from v2.backend.session_guard import verified_session_minute, validate_session_coverage, accept_verified_calendar, verified_range_session_minute, accepted_calendar_minute

IST = ZoneInfo("Asia/Kolkata")


def ms(y, m, d, h, minute):
    return int(datetime(y, m, d, h, minute, tzinfo=IST).timestamp() * 1000)


class VerifiedSessionScheduleTests(unittest.TestCase):
    def test_complete_calendar_requires_explicit_closed_days(self):
        friday, saturday, sunday = date(2026, 10, 16), date(2026, 10, 17), date(2026, 10, 18)
        sessions = {friday: (time(9, 15), time(15, 30)), saturday: None}
        self.assertFalse(validate_session_coverage(sessions, friday, sunday))
        sessions[sunday] = None
        self.assertTrue(validate_session_coverage(sessions, friday, sunday))

    def test_calendar_coverage_rejects_invalid_ranges_and_bounds(self):
        day = date(2026, 10, 15)
        self.assertFalse(validate_session_coverage({day: None}, date(2026, 10, 16), day))
        self.assertFalse(validate_session_coverage({day: ("09:15", "15:30")}, day, day))
        self.assertFalse(validate_session_coverage({day: (time(15, 30), time(9, 15))}, day, day))
        self.assertFalse(validate_session_coverage({}, day, day))

    def test_explicit_closed_day_rejects_all_ticks(self):
        closed = {date(2026, 10, 15): None}
        self.assertTrue(validate_session_coverage(
            closed, date(2026, 10, 15), date(2026, 10, 15)))
        for hour, minute in ((0, 0), (9, 15), (12, 0), (15, 29), (23, 59)):
            with self.subTest(hour=hour, minute=minute):
                self.assertIsNone(verified_session_minute(
                    ms(2026, 10, 15, hour, minute), closed))

    def test_calendar_requires_explicit_verification_and_source(self):
        day = date(2026, 10, 15)
        sessions = {day: (time(9, 15), time(15, 30))}
        self.assertIsNone(accept_verified_calendar(sessions, day, day, "NSE notice", False))
        self.assertIsNone(accept_verified_calendar(sessions, day, day, "", True))
        self.assertIsNone(accept_verified_calendar(sessions, day, day, "NSE notice", 1))
        accepted = accept_verified_calendar(sessions, day, day, "NSE notice", True)
        self.assertEqual(accepted, sessions)
        self.assertIsNot(accepted, sessions)

    def test_range_lookup_rejects_dates_outside_approved_period(self):
        day, next_day = date(2026, 10, 15), date(2026, 10, 16)
        sessions = {day: (time(9, 15), time(15, 30)),
                    next_day: (time(9, 15), time(15, 30))}
        self.assertEqual(verified_range_session_minute(
            ms(2026, 10, 15, 10, 0), sessions, day, day),
            datetime(2026, 10, 15, 10, 0))
        self.assertIsNone(verified_range_session_minute(
            ms(2026, 10, 16, 10, 0), sessions, day, day))

    def test_range_lookup_rejects_incomplete_calendar(self):
        day, next_day = date(2026, 10, 15), date(2026, 10, 16)
        sessions = {day: (time(9, 15), time(15, 30))}
        self.assertIsNone(verified_range_session_minute(
            ms(2026, 10, 15, 10, 0), sessions, day, next_day))

    def test_accepted_lookup_requires_verified_source_and_range(self):
        day, next_day = date(2026, 10, 15), date(2026, 10, 16)
        schedule = {day: (time(9, 15), time(15, 30)),
                    next_day: (time(9, 15), time(15, 30))}
        tick = ms(2026, 10, 15, 10, 0)
        self.assertIsNone(accepted_calendar_minute(
            tick, schedule, day, day, "NSE notice", False))
        self.assertIsNone(accepted_calendar_minute(
            tick, schedule, day, day, "", True))
        self.assertEqual(accepted_calendar_minute(
            tick, schedule, day, day, "NSE notice", True),
            datetime(2026, 10, 15, 10, 0))
        self.assertIsNone(accepted_calendar_minute(
            ms(2026, 10, 16, 10, 0), schedule, day, day, "NSE notice", True))

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

    def test_non_minute_aligned_boundaries_fail_closed(self):
        for bounds in ((time(9, 15, 1), time(15, 30)),
                       (time(9, 15), time(15, 30, 1)),
                       (time(9, 15, 0, 1), time(15, 30))):
            with self.subTest(bounds=bounds):
                self.assertIsNone(verified_session_minute(
                    ms(2026, 10, 15, 10, 0),
                    {date(2026, 10, 15): bounds}))

    def test_malformed_schedule_fails_closed(self):
        for schedule in (None, [], {date(2026, 10, 15): (time(15), time(9))},
                         {date(2026, 10, 15): ("09:15", "15:30")}):
            with self.subTest(schedule=schedule):
                self.assertIsNone(verified_session_minute(
                    ms(2026, 10, 15, 10, 0), schedule))


if __name__ == "__main__":
    unittest.main()
