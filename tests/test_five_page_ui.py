"""Static UI contract checks. Run with python -m unittest discover -s tests -p 'test_five_page_ui.py'."""
import pathlib
import re
import shutil
import subprocess
import tempfile
import unittest

HTML = pathlib.Path(__file__).resolve().parents[1] / "v2" / "frontend" / "index.html"


class FivePageUiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.html = HTML.read_text(encoding="utf-8")

    def test_embedded_javascript_parses(self):
        node = shutil.which("node")
        self.assertIsNotNone(node, "Node.js is required for UI syntax validation")
        scripts = re.findall(r"<script(?:\\s[^>]*)?>(.*?)</script>", self.html, re.S)
        self.assertTrue(scripts, "No inline JavaScript found")
        for script in scripts:
            if not script.strip():
                continue
            with tempfile.NamedTemporaryFile(mode="w", suffix=".js", encoding="utf-8") as js:
                js.write(script)
                js.flush()
                result = subprocess.run([node, "--check", js.name],
                                        capture_output=True, text=True)
                self.assertEqual(result.returncode, 0, result.stderr)

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
        self.assertIn("row?.candle_ist??row?.updated_at", self.html)
        self.assertIn("Date.parse(zoned)", self.html)
        self.assertIn("Date.now()-t<=180000", self.html)

    def test_freshness_prefers_completed_candle_time(self):
        self.assertIn("const stamp=row?.candle_ist??row?.updated_at", self.html)

    def test_scorecard_requires_fresh_aligned_scanner_data(self):
        self.assertIn("const validRating=x=>{const row=state.rows.find", self.html)
        self.assertIn("r&&fresh(row)&&['BUY','SELL'].includes(r.signal)&&row.signal===r.signal", self.html)

    def test_top_buy_rankings_require_fresh_aligned_scanner_data(self):
        self.assertIn("function verifiedStockBuy(x)", self.html)
        self.assertIn("fresh(x)&&fresh(row)&&row.signal==='BUY'", self.html)
        self.assertIn("state.ratings.filter(verifiedStockBuy)", self.html)

    def test_stock_analysis_requires_scanner_rating_direction_agreement(self):
        self.assertIn("r.signal===rating.signal&&['BUY','SELL'].includes(r.signal)", self.html)

    def test_stock_detail_uses_fresh_stock_specific_rating(self):
        self.assertIn("x.symbol===symbol&&x.type==='STOCK'&&x.rating_basis==='CANDLE_ONLY_HEURISTIC'&&fresh(x)", self.html)
        self.assertIn("const live=Boolean(state.sessionOpen&&fresh(r)&&rating&&r.signal===rating.signal", self.html)

    def test_signal_activity_request_starts_before_trade_history_wait(self):
        self.assertIn("const activityRequest=get('/api/v2/signal-activity')", self.html)
        self.assertLess(self.html.index("const activityRequest=get('/api/v2/signal-activity')"), self.html.index("const trades=await get('/api/v2/trades')"))
        self.assertIn("const result=await activityRequest", self.html)

    def test_recorded_pnl_requires_chronological_entry_exit(self):
        self.assertIn("Date.parse(x.sell_time)>=Date.parse(x.buy_time)", self.html)

    def test_recorded_pnl_requires_verified_entry_and_exit_timestamps(self):
        self.assertIn("istDate(x.buy_time)!=null&&istDate(x.sell_time)!=null", self.html)

    def test_daily_pnl_requires_positive_prices(self):
        self.assertIn("buy>0&&sell>0&&qty>0?(sell-buy)*qty:null", self.html)

    def test_daily_pnl_ist_date_is_locale_independent(self):
        self.assertIn("formatToParts(value)", self.html)
        self.assertIn("const today=istDay(new Date())", self.html)
        self.assertIn("return istDay(new Date(parsed))", self.html)

    def test_daily_pnl_rejects_timezone_ambiguous_exit_times(self):
        self.assertIn(r"if(!/(?:Z|[+-]\d{2}:?\d{2})$/i.test(raw))return null", self.html)

    def test_daily_pnl_uses_exit_date_not_entry_trade_date(self):
        self.assertIn("completed.filter(x=>istDate(x.sell_time)===today)", self.html)
        self.assertNotIn("x.sell_time||x.trade_date", self.html)

    def test_pnl_requires_recorded_entry_exit_and_quantity(self):
        self.assertIn("x.buy_price!=null&&x.sell_price!=null&&x.quantity!=null", self.html)
        self.assertIn("qty>0?(sell-buy)*qty:null", self.html)
        self.assertIn("pnlFor(x)!=null?num(pnlFor(x)):'Not verified'", self.html)

    def test_index_scanner_and_rating_must_agree(self):
        self.assertIn("const sig=aligned?score.signal:'WAIT'", self.html)
        self.assertIn("aligned?'VERIFIED FRESH':'WAIT / UNVERIFIED'", self.html)

    def test_index_buy_sell_requires_fresh_scanner_row_as_well(self):
        self.assertIn("const aligned=Boolean(live&&score&&r?.signal===score.signal", self.html)
        self.assertIn("aligned?esc(score.rating)+'/100':'—'", self.html)

    def test_index_signals_require_fresh_verified_index_ratings(self):
        self.assertIn("x.type==='INDEX'&&x.rating_basis==='CANDLE_ONLY_HEURISTIC'&&fresh(x)", self.html)
        self.assertIn("WAIT / UNVERIFIED", self.html)

    def test_premarket_bias_does_not_use_stored_index_readings(self):
        self.assertIn("const valid=rows.filter(r=>fresh(r)&&", self.html)
        self.assertIn("NO VERIFIED LIVE BIAS", self.html)
        self.assertIn("not an opening forecast", self.html)

    def test_scorecard_hides_stale_candle_scores(self):
        self.assertIn("const validRating=x=>", self.html)
        self.assertIn("y.rating_basis==='CANDLE_ONLY_HEURISTIC'&&fresh(y)", self.html)
        self.assertIn("const score=x=>validRating(x)?.rating??'—'", self.html)

    def test_top_buy_ranking_excludes_stale_ratings(self):
        self.assertIn("x.rating_basis==='CANDLE_ONLY_HEURISTIC'&&fresh(x)", self.html)
        self.assertIn(".sort((a,b)=>Number(b.rating)-Number(a.rating)).slice(0,10)", self.html)

    def test_stock_signals_require_live_verified_candle_rating(self):
        self.assertIn("const live=Boolean(state.sessionOpen&&fresh(r)&&rating&&r.signal===rating.signal", self.html)
        self.assertIn("x.type==='STOCK'&&x.rating_basis==='CANDLE_ONLY_HEURISTIC'&&fresh(x)", self.html)
        self.assertIn("WAIT — not independently verified fresh", self.html)

    def test_no_broker_execution_claim(self):
        self.assertIn("Order execution", self.html)
        self.assertIn("DISABLED", self.html)


if __name__ == "__main__":
    unittest.main()
