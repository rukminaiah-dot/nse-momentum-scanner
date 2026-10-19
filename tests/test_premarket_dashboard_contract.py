"""Offline safety contract for the research-only pre-market dashboard.

Does not require live feeds, credentials, a running scanner, or a database.
"""
from pathlib import Path
import unittest

from v2.backend.premarket_prediction import assess_premarket, WEIGHTS

ROOT = Path(__file__).resolve().parents[1]
HTML = ROOT / "v2" / "frontend" / "index.html"


class PremarketDashboardContractTests(unittest.TestCase):
    def test_dashboard_contains_research_panel_and_five_sources(self):
        page = HTML.read_text(encoding="utf-8")
        self.assertIn('id="premarket-study"', page)
        self.assertIn('id="premarket-outlook"', page)
        self.assertIn("GIFT NIFTY", page)
        self.assertIn("Global market cues", page)
        self.assertIn("RBI / macro news", page)
        self.assertIn("FII / DII flows", page)
        self.assertIn("Previous session trend", page)
        self.assertEqual(set(WEIGHTS), {
            "gift_nifty", "global_markets", "rbi_macro_news",
            "fii_dii", "previous_session"
        })

    def test_active_trades_are_separate_from_closed_history(self):
        page = HTML.read_text(encoding="utf-8")
        self.assertIn('id="active-trades"', page)
        self.assertIn('id="trades"', page)
        self.assertIn("trades.filter(t=>t.status!=='CLOSED')", page)
        self.assertIn("trades.filter(t=>t.status==='CLOSED')", page)
        self.assertIn("No active simulated trades", page)
        self.assertIn("Indicative P&L (quote freshness unverified)", page)
        self.assertIn("Last recorded price:", page)
        self.assertIn("Quote freshness:", page)
        self.assertIn("UNVERIFIED / NOT LIVE", page)
        self.assertNotIn("Live P&L:", page)

    def test_dashboard_shows_missing_automatic_sources(self):
        page = HTML.read_text(encoding="utf-8")
        self.assertIn("WAIT — automatic forecast unavailable", page)
        self.assertIn("Not connected: ", page)
        self.assertIn("Invalid or unverified: ", page)
        self.assertIn("data.automatic_forecast_ready===true", page)
        self.assertIn("data.status==='WAIT_LIVE_CONFIRMATION'", page)

    def test_missing_data_never_generates_a_direction(self):
        result = assess_premarket({"gift_nifty": 1})
        self.assertEqual(result.direction, "UNKNOWN")
        self.assertEqual(result.status, "WAIT_DATA_UNAVAILABLE")
        self.assertEqual(result.evidence_score, 0)

    def test_agreement_is_not_a_win_probability(self):
        page = HTML.read_text(encoding="utf-8")
        self.assertIn("not a win probability", page)
        self.assertIn("No automatic trades", page)
        self.assertIn("No prediction without all five sources", page)

    def test_complete_evidence_requires_live_confirmation(self):
        result = assess_premarket({key: 1 for key in WEIGHTS})
        self.assertEqual(result.direction, "BULLISH")
        self.assertEqual(result.evidence_score, 100)
        self.assertEqual(result.status, "WAIT_LIVE_CONFIRMATION")


if __name__ == "__main__":
    unittest.main()
