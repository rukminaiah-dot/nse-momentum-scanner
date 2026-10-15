"""Synthetic Upstox payload tests; no feed connection."""
import unittest
from datetime import datetime
from zoneinfo import ZoneInfo
from v2.backend.upstox_timestamp_extraction import inspect_decoded_message, summarize_decoded_messages

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

    def test_malformed_direct_feed_falls_back_to_nested(self):
        payload = {"currentTs": ms(15, 58), "feeds": {
            "A": {"ltpc": {}, "ff": {"marketFF": {"ltpc": {"ltt": ms(15, 28)}}}},
            "B": {"ltpc": "bad", "ff": [], "fullFeed": {
                "indexFF": {"ltpc": {"ltt": ms(15, 29)}}}},
            "C": {"ltpc": None, "ff": {"marketFF": None},
                  "fullFeed": {"marketFF": {"ltpc": {"ltt": ms(15, 28)}}}},
        }}
        records = inspect_decoded_message(payload, ms(15, 58))
        self.assertEqual(len(records), 3)
        self.assertTrue(all(row["trade_status"] == "STALE" for row in records))

    def test_aggregate_snapshot_vs_envelope_and_redaction(self):
        snapshot = {"currentTs": ms(15, 58), "feeds": {
            "PRIVATE_KEY": {"ff": {"marketFF": {"ltpc": {
                "ltt": ms(15, 28), "ltp": 8888}}}}}}
        recent = {"currentTs": ms(15, 58), "feeds": {
            "PRIVATE_KEY": {"ltpc": {"ltt": ms(15, 58), "ltp": 9999}}}}
        summary = summarize_decoded_messages([
            (snapshot, ms(15, 58)), (recent, ms(15, 58))])
        self.assertEqual(sum(row["count"] for row in summary), 2)
        self.assertEqual({row["trade_status"] for row in summary}, {"STALE", "FRESH"})
        self.assertEqual({row["envelope_status"] for row in summary}, {"FRESH"})
        self.assertNotIn("PRIVATE_KEY", str(summary))
        self.assertNotIn("8888", str(summary))
        self.assertNotIn("9999", str(summary))
        self.assertNotIn("event_ist", str(summary))

    def test_malformed_payload_is_ignored(self):
        self.assertEqual(inspect_decoded_message(None, ms(10, 0)), [])
        self.assertEqual(inspect_decoded_message({"feeds": []}, ms(10, 0)), [])
        self.assertEqual(inspect_decoded_message({"feeds": {"a": None}}, ms(10, 0)), [])


if __name__ == "__main__":
    unittest.main()
