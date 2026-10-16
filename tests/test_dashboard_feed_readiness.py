"""Offline contract checks for fail-closed dashboard feed readiness."""
from pathlib import Path
import unittest

HTML = Path(__file__).resolve().parents[1] / "v2/frontend/index.html"


class DashboardFeedReadinessTests(unittest.TestCase):
    def test_readiness_panel_is_present_and_polled(self):
        page = HTML.read_text(encoding="utf-8")
        self.assertIn('id="live-feed-readiness"', page)
        self.assertIn("fetch('/api/v2/live-screener-readiness'", page)
        self.assertIn("setInterval(loadLiveFeedReadiness,10000)", page)

    def test_unknown_status_fails_closed(self):
        page = HTML.read_text(encoding="utf-8")
        self.assertIn("Feed readiness unavailable; full coverage not verified.", page)
        self.assertIn("data.live_screener_ready===true", page)
        self.assertIn("data.partial_feed_activity_observed===true", page)
        self.assertIn("Broker orders: disabled", page)


if __name__ == "__main__":
    unittest.main()
