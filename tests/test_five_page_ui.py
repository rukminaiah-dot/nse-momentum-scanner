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

    def test_no_unverified_long_term_claim(self):
        self.assertIn("Long-term: Not verified", self.html)
        self.assertIn("function shortTrend", self.html) if "function shortTrend" in self.html else self.assertIn("const shortTrend=", self.html)

    def test_no_broker_execution_claim(self):
        self.assertIn("Order execution", self.html)
        self.assertIn("DISABLED", self.html)


if __name__ == "__main__":
    unittest.main()
