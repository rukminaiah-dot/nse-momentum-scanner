"""Synthetic Upstox payload tests; no feed connection."""
import unittest
from datetime import datetime
from zoneinfo import ZoneInfo
from v2.backend.upstox_timestamp_extraction import inspect_decoded_message

IST = ZoneInfo("Asia/Kolkata")


def ms(h, m):
    return int(datetime(2026, 10, 15, h, m, tzinfo=IST).timestamp() * 1000)


class ExtractionTests(unittest.TestCase):
    def test_nested_and_direct_feed_formats(self):
        payload = {"currentTs": str(ms(15, 58)), "feeds": {
            "SECRET_A": {"ltpc": {"ltt": str(ms(15, 28)), "ltp": 999}},
            "SECRET_B": {"ff": {"marketFF": {"ltpc": {"ltt": ms(15, 58)}}}},
            "SECRET_C": {"fullFeed": {"indexFF": {"ltpc": {"ltt": ms(15, 29)}}}},
        }}
        result = inspect_decoded_message(payload, ms(15, 58))
        self.assertEqual(len(result), 3)
        self.assertEqual(result[0]["trade_status"], "STALE")
        self.assertEqual(result[1]["trade_status"], "FRESH")
        self.assertEqual(result[0]["envelope_status"], "FRESH")
        self.assertNotIn("SECRET_A", str(result))
        self.assertNotIn("999", str(result))

    def test_malformed_payload_is_ignored(self):
        self.assertEqual(inspect_decoded_message(None, ms(10, 0)), [])
        self.assertEqual(inspect_decoded_message({"feeds": []}, ms(10, 0)), [])
        self.assertEqual(inspect_decoded_message({"feeds": {"a": None}}, ms(10, 0)), [])


if __name__ == "__main__":
    unittest.main()
