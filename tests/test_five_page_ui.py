"""Static UI contract checks. Run with python -m unittest discover -s tests -p 'test_five_page_ui.py'."""
import json
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

    def test_mobile_bottom_navigation_has_all_five_destinations(self):
        mobile = re.search(r'<nav class="mobile-nav" aria-label="Mobile pages">(.*?)</nav>', self.html, re.S)
        self.assertIsNotNone(mobile)
        self.assertEqual(re.findall(r'data-mobile-page="([^"]+)"', mobile.group(1)),
                         ["premarket", "pulse", "signals", "positions", "history"])
        for label in ("Pre-Market", "Dashboard", "Signals", "Positions", "Assistant"):
            self.assertIn(label, mobile.group(1))

    def test_assistant_page_has_guided_validation_and_request_controls(self):
        for required in ('id="assistant-log"', 'id="assistant-validate"',
                         'id="assistant-modify"', 'id="assistant-input"',
                         'id="assistant-send"', 'id="assistant-clear"'):
            self.assertIn(required, self.html)

    def test_assistant_validation_uses_loaded_data_and_states_limits(self):
        for required in ("function assistantValidation()", "state.rows.filter(fresh)",
                         "verifiedCandleScore(x)", "state.offlinePreview",
                         "does not compare quotes with NSE/Upstox independently"):
            self.assertIn(required, self.html)

    def test_assistant_explains_stock_signal_from_current_candle_evidence(self):
        for required in ("function assistantFindSymbol(text)",
                         "compact.includes('ICICIBANK')",
                         "function assistantExplainStock(symbol)",
                         "EMA-separation points", "momentum points",
                         "This score is not a probability or price prediction",
                         "otherwise the app should show WAIT"):
            self.assertIn(required, self.html)

    def test_assistant_prepares_reviewable_github_request_without_auto_submission(self):
        self.assertIn("function assistantIssueDraft(message,kind='modification')", self.html)
        self.assertIn("https://github.com/rukminaiah-dot/nse-momentum-scanner/issues/new?", self.html)
        self.assertIn("The request is not sent until you submit the GitHub form", self.html)
        self.assertIn('target="_blank" rel="noopener noreferrer"', self.html)

    def test_assistant_sends_limited_app_context_to_chat_proxy(self):
        for required in ("function assistantContext(question)",
                         "fetch('/api/assistant-chat'",
                         "messages:assistantHistory.slice(-10)",
                         "context:assistantContext(question)",
                         "Your message and this snapshot are sent to Google",
                         "free-tier prompts may be used to improve Google products",
                         "It has no live web search"):
            self.assertIn(required, self.html)
        self.assertNotIn("process.env.GEMINI_API_KEY", self.html)
        self.assertNotIn("AIza", self.html)
        self.assertIn("plain-language explanation", self.html)
        self.assertIn("check the relevant app or official source separately", self.html)
        self.assertIn("prepare a GitHub request for you to review", self.html)

    def test_chat_proxy_keeps_gemini_key_server_side_and_limits_requests(self):
        root = pathlib.Path(__file__).resolve().parents[1]
        proxy = (root / "v2/frontend/api/assistant-chat.js").read_text(encoding="utf-8")
        for required in ("process.env.GEMINI_API_KEY",
                         '"x-goog-api-key": process.env.GEMINI_API_KEY',
                         "https://generativelanguage.googleapis.com/v1beta/interactions",
                         "system_instruction: instructions",
                         "store: false",
                         "generation_config:",
                         "max_output_tokens: 700",
                         "thinking_level: \"low\"",
                         "function originAllowed(req)",
                         "function rateLimited(req)",
                         "ASSISTANT_NOT_CONFIGURED",
                         "one useful next check or improvement",
                         "Never imply that you searched it",
                         "the user must review and submit a GitHub request"):
            self.assertIn(required, proxy)

    def test_mobile_positions_route_opens_recorded_position_history(self):
        self.assertIn("function navigateMobile(id)", self.html)
        self.assertIn("if(id==='positions'){showPage('pulse')", self.html)
        self.assertIn("$('active-positions')?.closest('.card')?.scrollIntoView", self.html)
        self.assertIn("location.hash.slice(1)==='positions'", self.html)

    def test_mobile_signals_page_links_to_full_nse_200_scorecard(self):
        self.assertIn('id="browse-scorecard"', self.html)
        self.assertIn("$('browse-scorecard').onclick=()=>showPage('board')", self.html)

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

    def test_index_and_stock_detail_reject_malformed_candle_scores(self):
        self.assertIn("const aligned=Boolean(live&&score&&verifiedCandleScore(score)", self.html)
        self.assertIn("const live=Boolean(state.sessionOpen&&fresh(r)&&rating&&verifiedCandleScore(rating)", self.html)

    def test_candle_scores_must_be_present_and_within_zero_to_hundred(self):
        self.assertIn("const verifiedCandleScore=x=>", self.html)
        self.assertIn("x.rating!==null&&x.rating!==undefined&&x.rating!==''", self.html)
        self.assertIn("typeof x.rating!=='boolean'", self.html)
        self.assertIn("Number(x.rating)>=0&&Number(x.rating)<=100", self.html)
        self.assertIn("verifiedCandleScore(x)", self.html)
        self.assertIn("verifiedCandleScore(r)", self.html)

    def test_top_buy_rankings_require_fresh_aligned_scanner_data(self):
        self.assertIn("function verifiedStockBuy(x)", self.html)
        self.assertIn("fresh(x)&&fresh(row)&&row.signal==='BUY'", self.html)
        self.assertIn("state.ratings.filter(verifiedStockBuy)", self.html)

    def test_stock_analysis_requires_scanner_rating_direction_agreement(self):
        self.assertIn("r.signal===rating.signal&&['BUY','SELL'].includes(r.signal)", self.html)

    def test_stock_detail_uses_fresh_stock_specific_rating(self):
        self.assertIn("x.symbol===symbol&&x.type==='STOCK'&&x.rating_basis==='CANDLE_ONLY_HEURISTIC'&&fresh(x)&&verifiedCandleScore(x)", self.html)
        self.assertIn("const live=Boolean(state.sessionOpen&&fresh(r)&&rating&&verifiedCandleScore(rating)&&r.signal===rating.signal", self.html)

    def test_concurrent_trade_failure_is_caught_before_await(self):
        self.assertIn("const tradesResult=await tradesRequest;if(!tradesResult.ok)throw tradesResult.error", self.html)

    def test_signal_activity_request_starts_before_trade_history_wait(self):
        self.assertIn("const activityRequest=get('/api/v2/signal-activity')", self.html)
        self.assertLess(self.html.index("const activityRequest=get('/api/v2/signal-activity')"), self.html.index("const tradesResult=await tradesRequest"))
        self.assertIn("const tradesRequest=get('/api/v2/trades').then(value=>({ok:true,value}),error=>({ok:false,error}))", self.html)
        self.assertIn("const result=await activityRequest", self.html)

    def test_activity_history_uses_lookahead_for_exact_limit(self):
        api = (pathlib.Path(__file__).resolve().parents[1] / "v2/backend/api.py").read_text(encoding="utf-8")
        self.assertIn("ORDER BY GREATEST(COALESCE(sell_time, buy_time), buy_time) DESC NULLS LAST, id DESC LIMIT 501", api)
        self.assertIn("history_truncated = len(records) > 500", api)
        self.assertIn("records = records[:500]", api)

    def test_daily_pnl_blocks_invalid_completed_prices_any_day(self):
        self.assertIn("const invalidCompletedPrices=completed.filter(x=>pnlFor(x)==null)", self.html)
        self.assertIn("!invalidChronology.length&&!futureExits.length&&!futureEntries.length&&!invalidCompletedPrices.length&&!duplicateLifecycleIds&&!overlappingLifecycle&&todayClosed.length", self.html)

    def test_daily_pnl_blocks_undated_completed_entries(self):
        self.assertIn("const invalidEntries=completed.filter(x=>istDate(x.buy_time)==null)", self.html)
        self.assertIn("!undatedExits.length&&!invalidEntries.length&&!invalidChronology.length", self.html)

    def test_future_intraday_entries_and_exits_block_verified_pnl(self):
        self.assertIn("Date.parse(x.sell_time)>Date.now()+60000", self.html)
        self.assertIn("const futureEntries=[...active,...completed]", self.html)
        self.assertIn("Date.parse(x.buy_time)>Date.now()+60000", self.html)
        self.assertIn("!futureExits.length&&!futureEntries.length", self.html)

    def test_future_dated_exits_block_daily_pnl_and_chart(self):
        self.assertIn("const futureExits=completed.filter", self.html)
        self.assertIn("!invalidChronology.length&&!futureExits.length&&!futureEntries.length&&!invalidCompletedPrices.length", self.html)
        self.assertIn("sell_time > NOW() + INTERVAL '1 minute'", (pathlib.Path(__file__).resolve().parents[1] / "v2/backend/api.py").read_text(encoding="utf-8"))

    def test_pnl_chart_reports_reason_for_missing_verified_data(self):
        self.assertIn("const chartIssue=history&&history.status==='HISTORY_STORAGE_NOT_CONFIGURED'", self.html)
        self.assertIn("Recent recorded history contains invalid or incomplete exits", self.html)
        self.assertIn("Seven-day aggregate response failed validation", self.html)
        self.assertIn("history.history_truncated", self.html) if "history.history_truncated" in self.html else self.assertIn("activity.history_truncated", self.html)

    def test_seven_day_pnl_aggregate_is_read_only_ist_and_validates_all_exits(self):
        api = (pathlib.Path(__file__).resolve().parents[1] / "v2/backend/api.py").read_text(encoding="utf-8")
        self.assertIn('@app.get("/api/v2/pnl-history")', api)
        self.assertIn("datetime.now(ist).date()", api)
        self.assertIn("first_day = today - timedelta(days=6)", api)
        self.assertIn("WHERE sell_time >= %s AND sell_time < %s", api)
        self.assertIn("GROUP BY pnl_date", api)
        self.assertIn("invalid_count", api)
        self.assertIn("order_execution_enabled", api)
        self.assertIn("async function renderPnlChart()", self.html)
        self.assertIn("get('/api/v2/pnl-history')", self.html)
        self.assertIn("history.days_requested===7&&history.complete===true", self.html)

    def test_pnl_chart_discloses_persisted_source_and_nonbroker_status(self):
        self.assertIn("source: persisted daily_trade_history", self.html)
        self.assertIn("signal-based, not broker-confirmed", self.html)

    def test_pnl_chart_includes_exit_counts_and_accessible_labels(self):
        self.assertIn("x.exit_count===0?'no recorded exits':x.exit_count+' recorded exits", self.html)
        self.assertIn('role="group"', self.html)
        self.assertIn("numbers in parentheses are exit counts", self.html)
        self.assertIn("x.exit_count+' recorded exits, signal P&L '", self.html)

    def test_pnl_chart_distinguishes_no_exit_days_from_zero_profit(self):
        self.assertIn("Last seven IST calendar days", self.html)
        self.assertIn("No exits", self.html)
        self.assertIn("no-exit days are not zero P&L", self.html)

    def test_recorded_daily_pnl_chart_requires_complete_history(self):
        self.assertIn('id="pnl-chart"', self.html)
        self.assertIn("history.complete===true", self.html)
        self.assertIn("const validDays=Array.isArray(rows)&&rows.length===7", self.html)
        self.assertIn("P&L chart unavailable: '+esc(chartIssue)+'.", self.html)
        self.assertIn("signal-based, not broker-confirmed", self.html)
        self.assertIn("/api/v2/pnl-history", self.html)

    def test_overlapping_active_and_completed_entries_block_daily_total(self):
        self.assertIn("const overlappingLifecycle=active.some", self.html)
        self.assertIn("x.symbol===y.symbol&&x.buy_time===y.buy_time", self.html)
        self.assertIn("!duplicateLifecycleIds&&!overlappingLifecycle&&todayClosed.length", self.html)

    def test_whitespace_normalized_lifecycle_ids_cannot_duplicate(self):
        self.assertIn("String(other).trim()===String(id).trim()", self.html)

    def test_unsafe_numeric_lifecycle_ids_block_daily_pnl(self):
        self.assertIn("typeof id==='number'&&!Number.isSafeInteger(id)", self.html)

    def test_blank_or_non_scalar_lifecycle_ids_block_daily_pnl(self):
        self.assertIn("!['string','number'].includes(typeof id)", self.html)
        self.assertIn("String(id).trim()===''", self.html)

    def test_duplicate_active_and_completed_ids_block_daily_pnl(self):
        self.assertIn("const lifecycleIds=[...active,...completed]", self.html)
        self.assertIn("String(other).trim()===String(id).trim()", self.html)
        self.assertIn("!duplicateLifecycleIds&&!overlappingLifecycle&&todayClosed.length", self.html)

    def test_duplicate_completed_ids_block_daily_pnl(self):
        self.assertIn("const lifecycleIds=[...active,...completed].map", self.html)
        self.assertIn("!invalidCompletedPrices.length&&!duplicateLifecycleIds&&!overlappingLifecycle&&todayClosed.length", self.html)

    def test_array_signal_activity_payload_is_rejected(self):
        self.assertIn("typeof activity!=='object'||Array.isArray(activity)", self.html)

    def test_unknown_signal_activity_status_fails_closed(self):
        self.assertIn("!['RECORDED_HISTORY','HISTORY_STORAGE_NOT_CONFIGURED'].includes(activity.status)", self.html)

    def test_signal_activity_rejects_non_object_response(self):
        self.assertIn("!activity||typeof activity!=='object'", self.html)

    def test_malformed_recorded_history_is_not_shown_as_empty(self):
        self.assertIn("throw Error('Malformed signal history response')", self.html)
        self.assertIn("!Array.isArray(activity.completed)", self.html)
        self.assertIn("!Number.isSafeInteger(activity.incomplete_records)", self.html)
        self.assertIn("typeof activity.history_truncated!=='boolean'", self.html)

    def test_signal_activity_renders_before_legacy_trades_wait(self):
        self.assertLess(self.html.index("try{const result=await activityRequest;"), self.html.index("try{const tradesResult=await tradesRequest;"))
        self.assertIn("const activityRequest=get('/api/v2/signal-activity')", self.html)
        self.assertIn("const tradesRequest=get('/api/v2/trades')", self.html)

    def test_incomplete_lifecycle_records_block_verified_total(self):
        api = (pathlib.Path(__file__).resolve().parents[1] / "v2/backend/api.py").read_text(encoding="utf-8")
        self.assertIn('"incomplete_records": incomplete_records', api)
        self.assertIn("activity.incomplete_records===0", self.html)

    def test_daily_pnl_requires_complete_history_response(self):
        self.assertIn("activity.history_truncated===false", self.html)

    def test_daily_pnl_withholds_total_for_impossible_trade_chronology(self):
        self.assertIn("const invalidChronology=completed.filter", self.html)
        self.assertIn("const total=activity.history_truncated===false&&activity.incomplete_records===0&&!undatedExits.length&&!invalidEntries.length&&!invalidChronology.length", self.html)

    def test_daily_pnl_does_not_ignore_undated_completed_exits(self):
        self.assertIn("const undatedExits=completed.filter(x=>istDate(x.sell_time)==null)", self.html)
        self.assertIn("const total=activity.history_truncated===false&&activity.incomplete_records===0&&!undatedExits.length&&!invalidEntries.length&&!invalidChronology.length&&!futureExits.length&&!futureEntries.length&&!invalidCompletedPrices.length&&!duplicateLifecycleIds&&!overlappingLifecycle&&todayClosed.length", self.html)

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
        self.assertIn("const aligned=Boolean(live&&score&&verifiedCandleScore(score)&&r?.signal===score.signal", self.html)
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
        self.assertIn("const live=Boolean(state.sessionOpen&&fresh(r)&&rating&&verifiedCandleScore(rating)&&r.signal===rating.signal", self.html)
        self.assertIn("x.type==='STOCK'&&x.rating_basis==='CANDLE_ONLY_HEURISTIC'&&fresh(x)", self.html)
        self.assertIn("WAIT — not independently verified fresh", self.html)

    def test_no_broker_execution_claim(self):
        self.assertIn("Order execution", self.html)
        self.assertIn("DISABLED", self.html)

    def test_shadow_loss_learning_panel_is_connected_and_safe(self):
        api = (pathlib.Path(__file__).resolve().parents[1] / "v2/backend/api.py").read_text(encoding="utf-8")
        self.assertIn('@app.get("/api/v2/decision-learning")', api)
        self.assertIn("'/api/v2/decision-learning'", self.html)
        self.assertIn("function renderLearning()", self.html)
        self.assertIn('id="learning-losses"', self.html)
        self.assertIn("recommendations_enabled===true?'enabled':'disabled'", self.html)
        self.assertIn("broker orders disabled.", self.html)
        self.assertIn("300 points is an example, not a fixed threshold", self.html)

    def test_experimental_prediction_uses_only_fresh_aligned_index_evidence(self):
        self.assertIn('id="ai-prediction-panel"', self.html)
        self.assertIn('id="ai-prediction-status"', self.html)
        self.assertIn('function renderAiPrediction()', self.html)
        self.assertIn("const aligned=Boolean(row&&fresh(row)&&rating&&verifiedCandleScore(rating)&&row.signal===rating.signal", self.html)
        self.assertIn("if(!state.sessionOpen)", self.html)
        self.assertIn("if(valid.length<2)", self.html)
        self.assertIn("not a trained forecast", self.html)
        self.assertIn("No invented probability", self.html)
        self.assertIn("renderAiPrediction();", self.html)



    def test_vercel_rewrites_only_explicit_read_only_app_routes(self):
        root = pathlib.Path(__file__).resolve().parents[1]
        config = json.loads((root / "v2/frontend/vercel.json").read_text(encoding="utf-8"))
        expected = {
            "/api/v2/scanner": "https://nse-momentum-scanner-api.onrender.com/api/v2/scanner",
            "/api/v2/nifty200-stock-board": "https://nse-momentum-scanner-api.onrender.com/api/v2/nifty200-stock-board",
            "/api/v2/quality-ratings": "https://nse-momentum-scanner-api.onrender.com/api/v2/quality-ratings",
            "/api/v2/nifty200-feed-health": "https://nse-momentum-scanner-api.onrender.com/api/v2/nifty200-feed-health",
            "/api/v2/trades": "https://nse-momentum-scanner-api.onrender.com/api/v2/trades",
            "/api/v2/preview-status": "https://nse-momentum-scanner-api.onrender.com/api/v2/nifty200-feed-health",
            "/api/v2/decision-learning": "https://nse-v2-offline-preview.onrender.com/api/v2/decision-learning",
            "/api/v2/pnl-history": "https://nse-v2-offline-preview.onrender.com/api/v2/pnl-history",
            "/api/v2/signal-activity": "https://nse-v2-offline-preview.onrender.com/api/v2/signal-activity",
        }
        rewrites = config.get("rewrites", [])
        self.assertEqual(
            {item["source"]: item["destination"] for item in rewrites}, expected
        )
        for item in rewrites:
            self.assertNotIn("*", item["source"])

    def test_page_switcher_ignores_unknown_ids_and_hashes(self):
        self.assertIn("if(!target||!target.classList.contains('page'))return", self.html)
        self.assertIn("['premarket','pulse','analysis','board','signals','history'].includes(location.hash.slice(1))", self.html)

    def test_mobile_navigation_shows_all_page_buttons(self):
        self.assertIn("nav{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));overflow:visible}", self.html)
        self.assertIn("nav button{white-space:normal;line-height:1.25;min-height:44px}", self.html)

    def test_api_requests_time_out_instead_of_staying_on_loading_state(self):
        self.assertIn("new AbortController()", self.html)
        self.assertIn("setTimeout(()=>controller.abort(),12000)", self.html)
        self.assertIn("finally{clearTimeout(timer)}", self.html)


if __name__ == "__main__":
    unittest.main()
