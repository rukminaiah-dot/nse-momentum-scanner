"""Regression checks for the reversal evidence meter's honesty contract."""
import pathlib
import unittest

HTML = pathlib.Path(__file__).resolve().parents[1] / "v2" / "frontend" / "index.html"


class ReversalEvidenceUiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.html = HTML.read_text(encoding="utf-8")

    def test_meter_is_explicitly_checklist_match_not_probability(self):
        self.assertIn('Rule evidence meter · not probability', self.html)
        self.assertIn('share of four rule checklist conditions met', self.html)
        self.assertIn('It is not the probability of a reversal', self.html)

    def test_meter_requires_fresh_direction_and_all_current_confirmations(self):
        helper = self.html.split("function reversalEvidenceAssessment(rc)", 1)[1].split(
            "function renderPreReversal()", 1
        )[0]
        self.assertIn("price.status!=='LIVE_FRESH'", helper)
        self.assertIn("available.filter(Boolean).length<4", helper)
        self.assertIn("scored:false", helper)
        self.assertIn("Math.round(matched/4*100)", helper)

    def test_dashboard_exposes_rule_state_and_keeps_other_indices_unscored(self):
        dashboard = self.html.split("function renderTrendChanges()", 1)[1].split(
            "const verifiedCandleScore", 1
        )[0]
        self.assertIn("BOTTOM REVERSAL WATCH", dashboard)
        self.assertIn("TOP REVERSAL WATCH", dashboard)
        self.assertIn("HISTORICAL · no live reversal call", dashboard)
        self.assertIn("NIFTY reversal rules do not cover this index", dashboard)
        self.assertIn("not probability", dashboard)


if __name__ == "__main__":
    unittest.main()
