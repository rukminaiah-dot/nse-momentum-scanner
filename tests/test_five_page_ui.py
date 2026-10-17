"""Static UI contract checks. Run with python -m unittest discover -s tests -p 'test_five_page_ui.py'."""
import pathlib
import re
import unittest

HTML = pathlib.Path(__file__).resolve().parents[1] / "v2" / "frontend" / "index.html"


class FivePageUiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.html = HTML.read_text(encoding="utf-8")

    def test_five_navigation_pages_in_approved_order(self):
        nav = re.search(r'<nav aria-label="Main pages">(.*?)</nav>', self.html, re.S)
        self.assertIsNotNone(nav)
        self.assertEqual(re.findall(r'data-page="([^"]+)"', nav.group(1)),
                         ["pulse", "board", "analysis", "premarket", "history"])

    def test_mobile_favourites_and_limit(self):
        for required in ("board-mobile", "favourites-list", "fav-count",
                         "fav.length<20", "localStorage.setItem('nse-favourites-v1'"):
            self.assertIn(required, self.html)

    def test_dashboard_layout_persists(self):
        for required in ("initDashboardLayout();", "edit-layout", "reset-layout",
                         "nse-dashboard-section-order-v1"):
            self.assertIn(required, self.html)

    def test_dashboard_does_not_leave_empty_grid_wrappers(self):
        self.assertIn("if(!wrapper.children.length)wrapper.remove()", self.html)

    def test_no_unverified_long_term_claim(self):
        self.assertIn("Long-term: Not verified", self.html)
        self.assertIn("function shortTrend", self.html) if "function shortTrend" in self.html else self.assertIn("const shortTrend=", self.html)

    def test_rating_freshness_uses_candle_timestamp_and_timezone(self):
        self.assertIn("row?.updated_at??row?.candle_ist", self.html)
        self.assertIn("Date.parse(zoned)", self.html)
        self.assertIn("Date.now()-t<=180000", self.html)

    def test_top_buy_ranking_excludes_stale_ratings(self):
        self.assertIn("x.rating_basis==='CANDLE_ONLY_HEURISTIC'&&fresh(x)", self.html)
        self.assertIn(".sort((a,b)=>Number(b.rating)-Number(a.rating)).slice(0,10)", self.html)

    def test_stock_signals_require_live_verified_candle_rating(self):
        self.assertIn("state.sessionOpen&&fresh(r)&&rating&&fresh(rating)", self.html)
        self.assertIn("rating.rating_basis==='CANDLE_ONLY_HEURISTIC'", self.html)
        self.assertIn("WAIT — not independently verified fresh", self.html)

    def test_no_broker_execution_claim(self):
        self.assertIn("Order execution", self.html)
        self.assertIn("DISABLED", self.html)


if __name__ == "__main__":
    unittest.main()
