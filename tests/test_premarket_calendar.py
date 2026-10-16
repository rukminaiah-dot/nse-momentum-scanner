"""Offline exchange-calendar boundary checks; example dates are fixtures only."""
import unittest

from v2.backend.premarket_calendar import previous_trading_session_date as resolve_previous


def previous(**kwargs):
    return resolve_previous(calendar_verified=True, calendar_source='OFFLINE_TEST', **kwargs)


class PremarketCalendarTests(unittest.TestCase):
    def test_unverified_calendar_rejected(self):
        self.assertIsNone(resolve_previous(target_date_ist='2026-10-19', verified_session_dates=['2026-10-16', '2026-10-19']))

    def test_previous_session_skips_nontrading_days(self):
        dates = ["2026-10-15", "2026-10-16", "2026-10-19"]
        self.assertEqual(previous(target_date_ist="2026-10-19", verified_session_dates=dates),
                         "2026-10-16")

    def test_missing_target_fails_closed(self):
        self.assertIsNone(previous(target_date_ist="2026-10-20",
                                   verified_session_dates=["2026-10-16", "2026-10-19"]))

    def test_unordered_or_duplicate_dates_fail_closed(self):
        for dates in (["2026-10-19", "2026-10-16"],
                      ["2026-10-16", "2026-10-16"],
                      ["2026-10-16", "invalid"]):
            self.assertIsNone(previous(target_date_ist="2026-10-16",
                                       verified_session_dates=dates))

    def test_no_prior_session_in_calendar_fails_closed(self):
        self.assertIsNone(previous(target_date_ist="2026-10-16",
                                   verified_session_dates=["2026-10-16", "2026-10-19"]))


if __name__ == "__main__":
    unittest.main()
