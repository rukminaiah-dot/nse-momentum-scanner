"""Offline live screener readiness regression tests."""
import unittest
from v2.backend.live_feed_readiness import assess_live_feed


class LiveFeedReadinessTests(unittest.TestCase):
    def test_market_open_recent_ticks_required(self):
        ready = assess_live_feed(dict(market_session="OPEN", status="REPORTING",
                                      stocks_with_recent_ticks=15, universe_size=15,
                                      connection_last_event="CONNECTED"))
        self.assertTrue(ready["live_screener_ready"])
        self.assertFalse(ready["order_execution_enabled"])

    def test_partial_coverage_never_claims_ready(self):
        result = assess_live_feed(dict(market_session="OPEN", status="REPORTING",
                                       stocks_with_recent_ticks=15, universe_size=200,
                                       connection_last_event="CONNECTED"))
        self.assertTrue(result["partial_feed_activity_observed"])
        self.assertFalse(result["live_screener_ready"])
        self.assertIn("FULL_UNIVERSE_COVERAGE_NOT_VERIFIED", result["blockers"])

    def test_closed_market_fails_closed(self):
        result = assess_live_feed(dict(market_session="CLOSED", status="REPORTING",
                                       stocks_with_recent_ticks=15))
        self.assertFalse(result["live_screener_ready"])
        self.assertIn("MARKET_NOT_OPEN", result["blockers"])

    def test_heartbeat_without_ticks_fails(self):
        result = assess_live_feed(dict(market_session="OPEN", status="REPORTING",
                                       stocks_with_recent_ticks=0))
        self.assertFalse(result["live_screener_ready"])

    def test_missing_stale_and_invalid_fail(self):
        for health in (None, {}, dict(market_session="OPEN", status="STALE_REPORT",
                                      stocks_with_recent_ticks=100),
                       dict(market_session="OPEN", status="REPORTING",
                            stocks_with_recent_ticks=True)):
            self.assertFalse(assess_live_feed(health)["live_screener_ready"])


if __name__ == "__main__":
    unittest.main()
