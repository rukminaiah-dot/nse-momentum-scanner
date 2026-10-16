"""Offline checks for premarket source classifiers."""
import unittest
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from v2.backend.premarket_sources import (
    classify_percentage_change, gift_nifty_evidence, previous_session_evidence, assess_verified_sources
)

IST = ZoneInfo("Asia/Kolkata")
NOW = datetime(2026, 10, 16, 8, 30, tzinfo=IST)


class PremarketSourceTests(unittest.TestCase):
    def test_gift_nifty_direction(self):
        kwargs = dict(reference_close=25000, observed_at_ist=NOW.isoformat(), now=NOW)
        self.assertEqual(gift_nifty_evidence(last_price=25100, **kwargs), 1)
        self.assertEqual(gift_nifty_evidence(last_price=24900, **kwargs), -1)
        self.assertEqual(gift_nifty_evidence(last_price=25000, **kwargs), 0)

    def test_previous_session_direction(self):
        kwargs = dict(previous_open=25000, observed_at_ist=NOW.isoformat(), now=NOW)
        self.assertEqual(previous_session_evidence(previous_close=25100, **kwargs), 1)
        self.assertEqual(previous_session_evidence(previous_close=24900, **kwargs), -1)

    def test_stale_future_and_naive_observations_rejected(self):
        for stamp in ((NOW - timedelta(minutes=16)).isoformat(),
                      (NOW + timedelta(seconds=1)).isoformat(),
                      NOW.replace(tzinfo=None).isoformat(), "invalid"):
            self.assertIsNone(gift_nifty_evidence(
                last_price=25100, reference_close=25000,
                observed_at_ist=stamp, now=NOW))

    def test_bad_prices_and_nan_rejected(self):
        for price in (None, 0, -1, True, float("nan"), float("inf")):
            self.assertIsNone(gift_nifty_evidence(
                last_price=price, reference_close=25000,
                observed_at_ist=NOW.isoformat(), now=NOW))
        self.assertIsNone(classify_percentage_change(float("nan")))

    def test_verified_sources_do_not_force_partial_forecast(self):
        prediction, sources = assess_verified_sources({
            "gift_nifty": {
                "verified": True, "source": "OFFLINE_TEST", "instrument": "TEST_INDEX", "session_verified": True, "last_price": 25100, "reference_close": 25000,
                "observed_at_ist": NOW.isoformat()
            },
            "previous_session": {
                "verified": True, "source": "OFFLINE_TEST", "instrument": "TEST_INDEX", "session_verified": True, "previous_open": 25000, "previous_close": 24900,
                "observed_at_ist": NOW.isoformat()
            },
        }, now=NOW)
        self.assertEqual(prediction.direction, "UNKNOWN")
        self.assertEqual(prediction.status, "WAIT_DATA_UNAVAILABLE")
        self.assertEqual(sources["gift_nifty"]["value"], 1)
        self.assertEqual(sources["previous_session"]["value"], -1)
        self.assertEqual(sources["global_markets"]["status"], "NOT_CONNECTED")

    def test_unverified_observation_rejected(self):
        prediction, sources = assess_verified_sources({
            "gift_nifty": {
                "verified": False, "last_price": 25100, "reference_close": 25000,
                "observed_at_ist": NOW.isoformat()
            },
        }, now=NOW)
        self.assertEqual(prediction.direction, "UNKNOWN")
        self.assertIsNone(sources["gift_nifty"]["value"])

    def test_invalid_neutral_band_is_rejected(self):
        for band in (None, True, -1, float("nan"), float("inf")):
            self.assertIsNone(classify_percentage_change(1.0, neutral_band_pct=band))

    def test_previous_session_staleness(self):
        self.assertIsNone(previous_session_evidence(
            previous_open=25000, previous_close=25100,
            observed_at_ist=(NOW - timedelta(days=2)).isoformat(), now=NOW))


if __name__ == "__main__":
    unittest.main()
