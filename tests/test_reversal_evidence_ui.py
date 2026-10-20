"""Regression checks for the daily reversal evidence meter contract."""
import pathlib
import unittest

HTML = pathlib.Path(__file__).resolve().parents[1] / "v2" / "frontend" / "index.html"


class ReversalEvidenceUiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.html = HTML.read_text(encoding="utf-8")

    def test_meter_is_available_for_historical_and_live_evidence(self):
        self.assertIn("Long reversal evidence score · heuristic points, not probability", self.html)
        self.assertIn("rc.market_session==='CLOSED'?'HISTORICAL INPUT REVIEW'", self.html)
        self.assertIn("historical last stored readings", self.html)
        self.assertIn("Live/current inputs when verified", self.html)

    def test_meter_disclaims_probability_and_lists_missing_factors(self):
        self.assertIn("not a probability", self.html)
        self.assertIn('id="pm-rule-meter-factors"', self.html)
        self.assertIn("Missing or stale inputs stay unscored", self.html)
        self.assertIn("headline impact is shown separately and is not auto-scored", self.html)

    def test_frontend_displays_backend_score_not_its_own_unvalidated_guess(self):
        helper = self.html.split("function reversalEvidenceAssessment(rc)", 1)[1].split(
            "function renderPreReversal()", 1
        )[0]
        self.assertIn("rc.reversal_evidence", helper)
        self.assertNotIn("Math.round(", helper)
        self.assertIn("evidence.score_points", self.html)
        self.assertIn("evidence.assessed_factors", self.html)

    def test_dashboard_exposes_nifty_states_and_limits_other_index_claims(self):
        dashboard = self.html.split("function renderTrendChanges()", 1)[1].split(
            "const verifiedCandleScore", 1
        )[0]
        self.assertIn("BOTTOM REVERSAL WATCH", dashboard)
        self.assertIn("TOP REVERSAL WATCH", dashboard)
        self.assertIn("HISTORICAL · no live reversal call", dashboard)
        self.assertIn("NIFTY reversal rules do not cover this index", dashboard)
        self.assertIn("verified 500-point move against the prior trend", dashboard)


if __name__ == "__main__":
    unittest.main()
