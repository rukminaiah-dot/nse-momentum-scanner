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
        self.assertIn("live/current inputs when verified", self.html)

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

    def test_dashboard_uses_intraday_shift_feed_not_long_horizon_reversal_rules(self):
        dashboard = self.html.split("function renderTrendChanges()", 1)[1].split(
            "function mergeDailyChangeContext", 1
        )[0]
        self.assertIn("state.trendChanges", dashboard)
        self.assertIn("['PAPER_BUY','PAPER_SELL','WAIT']", dashboard)
        self.assertIn("x.data_status==='LIVE_FRESH'", dashboard)
        self.assertIn("No live signal is assigned.", dashboard)
        self.assertIn("21-session average", dashboard)
        self.assertIn("Volume: not available for spot indices.", dashboard)
        self.assertIn("historical", dashboard)
        self.assertNotIn("BOTTOM REVERSAL WATCH", dashboard)
        self.assertNotIn("500-point move", dashboard)
        self.assertIn("Loading verified 15-minute candles", dashboard)
        self.assertIn("unavailable/stale", dashboard)
        self.assertIn("/api/v2/experimental/15m-index-trends", self.html)

    def test_timestamped_news_is_related_to_the_verified_short_term_trend(self):
        helper = HTML.parent / "news_trend_relation.js"
        source = helper.read_text(encoding="utf-8")
        self.assertIn('src="./news_trend_relation.js"', self.html)
        self.assertIn("window.classifyNewsTrendRelation(newsImpact,newsTrend)", self.html)
        self.assertIn("Supports reversal", source)
        self.assertIn("Supports continuation", source)
        self.assertIn("Neutral / unclear", self.html)
        self.assertIn("trend unverified", source)
        self.assertIn("not automatically scored", self.html)


if __name__ == "__main__":
    unittest.main()
