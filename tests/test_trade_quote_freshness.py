"""Offline tests for simulated trade quote freshness."""
import unittest
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from v2.backend.trade_quote_freshness import quote_freshness

NOW = datetime(2026, 10, 16, 10, 0, tzinfo=ZoneInfo("Asia/Kolkata"))


class QuoteFreshnessTests(unittest.TestCase):
    def test_unverified_timestamp_never_claims_live(self):
        self.assertEqual(quote_freshness(observed_at_ist=NOW.isoformat(), now=NOW), "UNVERIFIED")

    def test_recent_verified_quote(self):
        self.assertEqual(quote_freshness(observed_at_ist=(NOW-timedelta(seconds=20)).isoformat(),
                                         timestamp_verified=True, now=NOW), "VERIFIED_FRESH")

    def test_stale_and_future_rejected(self):
        self.assertEqual(quote_freshness(observed_at_ist=(NOW-timedelta(minutes=3)).isoformat(),
                                         timestamp_verified=True, now=NOW), "STALE")
        self.assertEqual(quote_freshness(observed_at_ist=(NOW+timedelta(seconds=1)).isoformat(),
                                         timestamp_verified=True, now=NOW), "FUTURE_TIMESTAMP")

    def test_naive_or_invalid_timestamp_rejected(self):
        for value in ("2026-10-16T10:00:00", "invalid", None):
            self.assertEqual(quote_freshness(observed_at_ist=value,
                                             timestamp_verified=True, now=NOW), "UNVERIFIED")


if __name__ == "__main__":
    unittest.main()
