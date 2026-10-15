"""No broker access: illustrative tick timestamp diagnostic cases."""
import unittest
from datetime import datetime
from zoneinfo import ZoneInfo
from v2.backend.timestamp_audit import inspect_tick_timestamp

IST = ZoneInfo("Asia/Kolkata")


def ms(h, m, s=0):
    return int(datetime(2026, 10, 15, h, m, s, tzinfo=IST).timestamp() * 1000)


class TimestampAuditTests(unittest.TestCase):
    def test_fresh_post_close_event_is_not_proof_of_valid_session(self):
        result = inspect_tick_timestamp(ms(15, 58), ms(15, 58, 1))
        self.assertEqual(result["status"], "FRESH")
        self.assertEqual(result["session_action"], "UNKNOWN")
        self.assertIn("15:58", result["event_ist"])

    def test_rejected_calendar_action_is_preserved(self):
        result = inspect_tick_timestamp(ms(15, 58), ms(15, 58, 1),
                                        session_action="REJECT")
        self.assertEqual(result["session_action"], "REJECT")

    def test_seconds_and_milliseconds_equivalent(self):
        self.assertEqual(inspect_tick_timestamp(ms(10, 0) // 1000, ms(10, 0)),
                         inspect_tick_timestamp(ms(10, 0), ms(10, 0)))

    def test_stale_and_future_are_distinguished(self):
        self.assertEqual(inspect_tick_timestamp(ms(10, 0), ms(10, 3))["status"], "STALE")
        self.assertEqual(inspect_tick_timestamp(ms(10, 0, 10), ms(10, 0))["status"], "FUTURE")

    def test_ambiguous_and_fractional_magnitudes_fail_closed(self):
        arrival = ms(10, 0)
        for value in (12345678901, 123456789012, 12345678901234,
                      arrival + 0.5, "1e309"):
            self.assertEqual(inspect_tick_timestamp(value, arrival)["status"], "INVALID")
        for value in (arrival // 1000, arrival + 0.5, float("inf")):
            self.assertEqual(inspect_tick_timestamp(arrival, value)["status"], "INVALID")

    def test_invalid_values_fail_closed(self):
        for value in (None, True, "", "not-a-number", -1, float("nan"), float("inf")):
            self.assertEqual(inspect_tick_timestamp(value, ms(10, 0))["status"], "INVALID")
        self.assertEqual(inspect_tick_timestamp(ms(10, 0), False)["status"], "INVALID")


if __name__ == "__main__":
    unittest.main()
