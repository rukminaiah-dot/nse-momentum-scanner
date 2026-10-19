"""Offline source-adapter regression tests; no market requests."""
import unittest
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from v2.backend.premarket_sources import (
    global_markets_evidence, fii_dii_evidence, rbi_macro_news_evidence,
    assess_verified_sources,
)

NOW = datetime(2026, 10, 16, 8, 30, tzinfo=ZoneInfo("Asia/Kolkata"))


class AdditionalPremarketSourcesTests(unittest.TestCase):
    def test_global_markets_requires_multiple_finite_benchmarks(self):
        self.assertEqual(global_markets_evidence(
            market_changes_pct={"US": 1.2, "ASIA": 0.6},
            observed_at_ist=NOW.isoformat(), now=NOW), 1)
        self.assertIsNone(global_markets_evidence(
            market_changes_pct={"US": 1.2}, observed_at_ist=NOW.isoformat(), now=NOW))
        self.assertIsNone(global_markets_evidence(
            market_changes_pct={"US": float("nan"), "ASIA": 0},
            observed_at_ist=NOW.isoformat(), now=NOW))

    def test_institutional_flows_require_session_provenance(self):
        args = dict(fii_net_crore=-200, dii_net_crore=300,
                    observed_at_ist=NOW.isoformat(), session_date_ist="2026-10-15",
                    expected_previous_session_date_ist="2026-10-15", now=NOW)
        self.assertEqual(fii_dii_evidence(**args), 1)
        args["expected_previous_session_date_ist"] = "2026-10-14"
        self.assertIsNone(fii_dii_evidence(**args))

    def test_macro_requires_explicit_event_and_recent_adjudication(self):
        self.assertEqual(rbi_macro_news_evidence(
            event_bias=-1, event_id="TEST_EVENT",
            observed_at_ist=NOW.isoformat(), now=NOW), -1)
        self.assertIsNone(rbi_macro_news_evidence(
            event_bias=True, event_id="TEST_EVENT",
            observed_at_ist=NOW.isoformat(), now=NOW))
        self.assertIsNone(rbi_macro_news_evidence(
            event_bias=1, event_id="TEST_EVENT",
            observed_at_ist=(NOW-timedelta(hours=5)).isoformat(), now=NOW))

    def test_five_verified_test_inputs_are_research_only(self):
        common = dict(verified=True, source="OFFLINE_FIXTURE",
                      instrument="TEST", session_verified=True,
                      observed_at_ist=NOW.isoformat())
        observations = {
            "gift_nifty": dict(common, last_price=25100, reference_close=25000),
            "global_markets": dict(common, market_changes_pct={"US": 1, "ASIA": 1}),
            "rbi_macro_news": dict(common, event_bias=1, event_id="TEST_EVENT"),
            "fii_dii": dict(common, fii_net_crore=100, dii_net_crore=200,
                            session_date_ist="2026-10-15",
                            expected_previous_session_date_ist="2026-10-15"),
            "previous_session": dict(common, previous_open=25000,
                                     previous_close=25100, session_date_ist="2026-10-15",
                                     expected_previous_session_date_ist="2026-10-15"),
        }
        prediction, sources = assess_verified_sources(observations, now=NOW)
        self.assertEqual(prediction.direction, "BULLISH")
        self.assertEqual(prediction.status, "WAIT_LIVE_CONFIRMATION")
        self.assertTrue(all(s["status"] == "VERIFIED" for s in sources.values()))


if __name__ == "__main__":
    unittest.main()
