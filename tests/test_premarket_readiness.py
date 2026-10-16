"""Offline checks for premarket readiness and mandatory live confirmation."""
import unittest
from datetime import datetime
from zoneinfo import ZoneInfo
from v2.backend.premarket_prediction import assess_premarket, WEIGHTS
from v2.backend.premarket_readiness import premarket_readiness

NOW = datetime(2026, 10, 16, 8, 30, tzinfo=ZoneInfo("Asia/Kolkata"))


class PremarketReadinessTests(unittest.TestCase):
    def test_missing_sources_fail_closed(self):
        prediction = assess_premarket({}, now=NOW)
        result = premarket_readiness(prediction, {})
        self.assertFalse(result["research_forecast_ready"])
        self.assertFalse(result["trade_signal_ready"])
        self.assertIn("SOURCE_NOT_VERIFIED:gift_nifty", result["blockers"])
        self.assertIn("LIVE_MARKET_CONFIRMATION_REQUIRED", result["blockers"])

    def test_verified_research_still_requires_live_confirmation(self):
        prediction = assess_premarket({key: 1 for key in WEIGHTS}, now=NOW)
        sources = {key: {"status": "VERIFIED"} for key in WEIGHTS}
        result = premarket_readiness(prediction, sources)
        self.assertTrue(result["research_forecast_ready"])
        self.assertFalse(result["trade_signal_ready"])
        self.assertFalse(result["order_execution_enabled"])
        self.assertEqual(result["live_market_confirmation"], "NOT_CONNECTED")

    def test_invalid_source_blocks_forecast(self):
        prediction = assess_premarket({key: 0 for key in WEIGHTS}, now=NOW)
        sources = {key: {"status": "VERIFIED"} for key in WEIGHTS}
        sources["fii_dii"] = {"status": "INVALID_OR_UNVERIFIED"}
        self.assertFalse(premarket_readiness(prediction, sources)["research_forecast_ready"])


if __name__ == "__main__":
    unittest.main()
