"""Offline contract checks for fail-closed pre-market evidence API."""
import unittest
from unittest.mock import patch
from datetime import datetime
from zoneinfo import ZoneInfo

from v2.backend.premarket_sources import assess_verified_sources

IST = ZoneInfo("Asia/Kolkata")
NOW = datetime(2026, 10, 16, 8, 30, tzinfo=IST)


class PremarketAPIContractTests(unittest.TestCase):
    def test_empty_sources_return_wait_and_all_categories(self):
        prediction, sources = assess_verified_sources({}, now=NOW)
        self.assertEqual(prediction.status, "WAIT_DATA_UNAVAILABLE")
        self.assertEqual(prediction.direction, "UNKNOWN")
        self.assertEqual(len(sources), 5)
        self.assertTrue(all(row["status"] == "NOT_CONNECTED" for row in sources.values()))

    def test_two_verified_sources_still_cannot_predict(self):
        prediction, sources = assess_verified_sources({
            "gift_nifty": {"verified": True, "source": "OFFLINE_TEST", "instrument": "TEST_INDEX", "session_verified": True, "last_price": 25100,
                           "reference_close": 25000, "observed_at_ist": NOW.isoformat()},
            "previous_session": {"verified": True, "source": "OFFLINE_TEST", "instrument": "TEST_INDEX", "session_verified": True, "previous_open": 25000,
                                 "previous_close": 25100, "session_date_ist": "2026-10-15", "expected_previous_session_date_ist": "2026-10-15", "observed_at_ist": NOW.isoformat()},
        }, now=NOW)
        self.assertEqual(prediction.direction, "UNKNOWN")
        self.assertEqual(prediction.status, "WAIT_DATA_UNAVAILABLE")
        self.assertEqual(sum(s["status"] == "VERIFIED" for s in sources.values()), 2)

    def test_unknown_source_rejected(self):
        with self.assertRaises(ValueError):
            assess_verified_sources({"untrusted_source": {}}, now=NOW)


if __name__ == "__main__":
    unittest.main()
