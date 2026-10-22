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

    def test_nse200_board_renders_as_soon_as_its_api_responds(self):
        load = re.search(r"async function load\(\)\s*\{(.*?)\n\}", self.html, re.S)
        self.assertIsNotNone(load)
        self.assertRegex(load.group(1), r"const boardPromise=get\(corePaths\[1\]\)")
        self.assertIsNotNone(re.search(
            r"boardPromise\.then\(value=>\{.*?state\.board=.*?renderBoard\(\);",
            load.group(1), re.S,
        ))
        self.assertIn(
            "Promise.all([boardPromise,Promise.allSettled(otherPaths.map(get))])",
            load.group(1),
        )

    def test_favourite_summary_does_not_show_legacy_5m_rating_columns(self):
        self.assertIn(
            "const favouriteHeaders=['Rank','Favourite','Stock','Session change %','Last price','Quote']",
            self.html,
        )
        self.assertIn("15-minute candle, RVOL, EMA and Stoch RSI appear in the paper readout below.", self.html)

    def test_saved_favourites_have_separate_15m_readout(self):
        self.assertIn("function refreshFavourite15m", self.html)
        self.assertIn("favorite_analysis", self.html)
        self.assertIn("Stoch RSI K / D", self.html)
        self.assertIn("symbols='+encodeURIComponent(symbols.join(','))", self.html)

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

    def test_desktop_navigation_calls_page_five_settings(self):
        nav = re.search(r'<nav aria-label="Main pages">(.*?)</nav>', self.html, re.S)
        self.assertIsNotNone(nav)
        self.assertRegex(nav.group(1), r'data-page="history">05 · Settings</button>')

    def test_mobile_navigation_matches_the_five_primary_pages(self):
        mobile = re.search(r'<nav class="mobile-nav" aria-label="Mobile pages">(.*?)</nav>', self.html, re.S)
        self.assertIsNotNone(mobile)
        self.assertEqual(re.findall(r'data-mobile-page="([^"]+)"', mobile.group(1)),
                         ["pulse", "board", "analysis", "premarket", "history"])
        for label in ("Dashboard", "NSE 200", "Analysis", "Pre-Market", "Settings"):
            self.assertIn(label, mobile.group(1))

    def test_mobile_page_selector_is_at_the_top_and_stays_visible(self):
        header_end = self.html.index("</header>")
        nav_start = self.html.index('<nav class="mobile-nav"')
        main_start = self.html.index("<main>")
        self.assertLess(header_end, nav_start)
        self.assertLess(nav_start, main_start)
        self.assertIn(".mobile-nav{position:sticky;top:0", self.html)
        self.assertNotIn(".mobile-nav{position:fixed", self.html)

    def test_phone_layout_constrains_page_width_and_wraps_content(self):
        self.assertIn("html,body{max-width:100%;overflow-x:clip}", self.html)
        self.assertIn("@media(max-width:900px),(pointer:coarse)", self.html)
        self.assertIn("grid-template-columns:repeat(5,minmax(0,1fr))", self.html)
        self.assertIn(".toolbar input{flex:1 1 100%;width:100%}", self.html)
        self.assertIn("h1,h2,p,.notice,.pill,.small,td,th{overflow-wrap:anywhere}", self.html)

    def test_partial_api_failures_are_reported_even_when_scanner_endpoint_works(self):
        self.assertIn("apiFailures:[]", self.html)
        self.assertIn("state.apiFailures=coreOk.flatMap", self.html)
        self.assertIn("const partial=ready&&failures.length>0", self.html)
        self.assertIn("PARTIAL DATA — ", self.html)
        self.assertIn("Some data sources could not be reached:", self.html)

    def test_settings_page_exposes_real_customization_and_discloses_unavailable_alerts(self):
        for required in ('<h1>Settings &amp; Customization</h1>', 'id="settings-layout"',
                         'id="settings-favourites-link"', "Alert delivery is not connected",
                         "No alert toggles are shown", "id=\"assistant-log\""):
            self.assertIn(required, self.html)

    def test_scorecard_filters_are_limited_to_verified_buy_sell_and_historical_data(self):
        for key in ("ALL", "BUY", "SELL", "HISTORICAL"):
            self.assertIn(f'data-board-filter="{key}"', self.html)
        self.assertIn("const counts={ALL:searched.length", self.html)
        self.assertIn("button.setAttribute('aria-pressed',String(key===boardFilter))", self.html)

    def test_stock_analysis_states_ohlc_chart_data_is_not_connected(self):
        self.assertIn("<h2>Price chart &amp; candle history</h2>", self.html)
        self.assertIn("Historical OHLC candles are not included in the current scanner response", self.html)

    def test_trade_and_learning_panels_use_persistent_pnl_history(self):
        api = (pathlib.Path(__file__).resolve().parents[1] / "v2/backend/api.py").read_text(encoding="utf-8")
        trades = api[api.index('@app.get("/api/v2/trades")'):api.index('from fastapi.responses import FileResponse')]
        learning = api[api.index('@app.get("/api/v2/decision-learning")'):api.index('@app.get("/history")')]
        self.assertIn("rows = get_daily_trade_history()", trades)
        self.assertNotIn("sqlite3.connect(DB_PATH", trades)
        self.assertIn("FROM daily_trade_history", learning)
        self.assertIn("learning_report_from_records(rows)", learning)

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

    def test_assistant_explains_read_only_learning_summary(self):
        for required in ("function assistantExplainLearning(question='')", "state.learning",
                         "gross_loss_reasons", "gross_losses_by_nifty_recovery_state",
                         "Read-only AI Learning", "Chat cannot edit training data or model settings",
                         "read-only AI Learning summaries"):
            self.assertIn(required, self.html)

    def test_assistant_learning_summary_formats_loaded_records(self):
        node = shutil.which("node")
        self.assertIsNotNone(node, "Node.js is required for assistant behavior validation")
        start = self.html.index("function assistantExplainLearning(question='')")
        end = self.html.index("function assistantLocalReply", start)
        function_source = self.html[start:end].strip()
        learning = {
            "model": {"status": "SHADOW_VALIDATED"},
            "complete_records": 4,
            "gross_loss_count": 2,
            "invalid_records_excluded": 1,
            "gross_loss_reasons": {"STOP_LOSS": 2, "TARGET_EXIT": 3, "INVALID_NEGATIVE": -5},
            "gross_losses_by_nifty_recovery_state": {"RECOVERING": 1},
            "recommendations_enabled": False,
        }
        script = "\n".join([
            'const assert = require("node:assert/strict");',
            "const state = {learning: " + json.dumps(learning) + "};",
            function_source,
            "const summary = assistantExplainLearning();",
            'assert.ok(summary.includes(String.fromCharCode(10) + "• Model status:"));',
            'assert.match(summary, /Model status: SHADOW VALIDATED/);',
            'assert.match(summary, /Complete recorded outcomes: 4/);',
            'assert.match(summary, /Gross losses: 2/);',
            'assert.match(summary, /STOP LOSS: 2/);',
            'assert.match(summary, /RECOVERING: 1/);',
            'assert.match(summary, /Recommendations: disabled/);',
            'assert.match(summary, /cannot edit training data or model settings/);',
            'const shadow = assistantExplainLearning("What does shadow mean?");',
            'assert.match(shadow, /reviews saved signal outcomes/);',
            'assert.match(shadow, /without changing the scanner/);',
            'const recommendation = assistantExplainLearning("Are recommendations enabled?");',
            'assert.match(recommendation, /Recommendations are disabled/);',
            'assert.match(recommendation, /read-only from chat/);',
            'const loss = assistantExplainLearning("Which loss reason occurs most?");',
            'assert.match(loss, /Most frequently recorded loss exit category: TARGET EXIT/);',
            'assert.match(loss, /do not prove what caused a loss or predict future results/);',
            'assert.doesNotMatch(loss, /INVALID NEGATIVE/);',
            "state.learning = null;",
            'assert.match(assistantExplainLearning(), /summary is unavailable/);',
        ])
        result = subprocess.run([node, "-e", script], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_assistant_uses_local_checks_and_explicit_google_search_handoff(self):
        for required in ("function assistantGoogleSearch(question)",
                         "function assistantLocalReply(question)",
                         "assistantGoogleSearch(value)",
                         "https://www.google.com/search?",
                         "Your question will be sent to Google only if you tap this link",
                         "does not send your chat to an AI provider"):
            self.assertIn(required, self.html)
        for removed in ("assistant-chat", "GEMINI_API_KEY",
                        "generativelanguage.googleapis.com", "assistantAskGemini"):
            self.assertNotIn(removed, self.html)

    def test_positions_deep_link_opens_recorded_position_history(self):
        self.assertIn("function showPositions()", self.html)
        self.assertIn("$('active-positions')?.closest('.card')?.scrollIntoView", self.html)
        self.assertIn("location.hash.slice(1)==='positions'", self.html)

    def test_mobile_signals_page_links_to_full_nse_200_scorecard(self):
        self.assertIn('id="browse-scorecard"', self.html)
        self.assertIn("$('browse-scorecard').onclick=()=>showPage('board')", self.html)

    def test_nse200_search_matches_company_names_and_exposes_favourite_action(self):
        self.assertIn('placeholder="Search symbol or company (e.g. ICICI Bank)"', self.html)
        self.assertIn('id="board-search-status"', self.html)
        self.assertIn("symbol.includes(q)||q.includes(symbol)", self.html)
        self.assertIn("aria-pressed=\"'+String(fav.includes(x.symbol))+'\"", self.html)
        helper = re.search(r"function normalizeBoardSearch\(value\)\{[^}]+\}", self.html)
        self.assertIsNotNone(helper, "Search text normalization helper is missing")
        script = helper.group(0) + "\nif(normalizeBoardSearch('Icici bank')!=='ICICIBANK') process.exit(1);"
        result = subprocess.run(["node", "-e", script], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_favourites_show_separate_15m_paper_indicators(self):
        for required in (
            'id="favourites-15m"',
            '15m candle · O/H/L/C (IST)',
            '15-minute Favourite Signals',
            "'5m Score / last'",
            "'EMA20 / EMA50 · trend'",
            "'Stoch RSI K / D'",
            "indicator.stoch_k",
            "indicator.stoch_d",
            "HISTORICAL · ",
            "No live signal is assigned",
        ):
            self.assertIn(required, self.html)

    def test_mobile_favourites_and_limit(self):
        for required in ("board-mobile", "favourites-list", "fav-count",
                         "fav.length<20", "localStorage.setItem('nse-favourites-v1'"):
            self.assertIn(required, self.html)

    def test_dashboard_storage_handlers_exist_for_board_controls(self):
        for required in ("function getFavourites()", "function toggleFavourite(symbol)",
                         "function rememberLastRatings()", "localStorage.setItem(SCORE_CACHE_KEY"):
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

    def test_live_health_distinguishes_tick_coverage_from_fresh_scanner_candles(self):
        self.assertIn("Upstox tick coverage", self.html)
        self.assertIn("Fresh scanner candles", self.html)
        self.assertIn("data_status==='LIVE_FRESH'", self.html)
        self.assertIn("excluded from current signals", self.html)
        self.assertIn("continuous connection guarantee", self.html)
        self.assertIn("Freshness limit: 3 minutes.", self.html)

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

    def test_dashboard_summary_separates_fresh_stock_setups_from_stale_data(self):
        self.assertIn('id="live-call-summary"', self.html)
        self.assertIn("function renderLiveCallSummary()", self.html)
        self.assertIn("FRESH STOCK SETUPS:", self.html)
        self.assertIn("x?.setup_data_fresh===true", self.html)
        self.assertIn("NO FRESH STOCK SETUP DATA:", self.html)
        self.assertIn("latest setup data ", self.html)
        self.assertIn("checked ", self.html)
        self.assertIn("stale/awaiting", self.html)
        self.assertIn("Index readings are checked separately", self.html)
        self.assertIn("stale index data does not change these stock setup counts", self.html)
        self.assertIn("Market closed: stored setup rows are historical", self.html)

    def test_stock_setup_api_reports_freshness_separately(self):
        api_path = HTML.parents[1] / "backend" / "api.py"
        api = api_path.read_text(encoding="utf-8")
        self.assertIn('"fresh_setup_count": 0', api)
        self.assertIn('"stale_setup_count": 0', api)
        self.assertIn('"setup_data_fresh": False', api)
        self.assertIn('row["setup_data_fresh"] = bool(open_now and fresh)', api)
        self.assertIn('output["status"] = "NO_FRESH_SETUPS"', api)

    def test_stock_setup_rankings_use_all_fresh_api_candidates(self):
        self.assertIn("/api/v2/stock-setups", self.html)
        self.assertIn("function renderStockSetups(hostId)", self.html)
        self.assertIn("['WATCH','TRIGGERED','CONFIRMED','INVALID']", self.html)
        self.assertIn("Heuristic rank ", self.html)
        self.assertIn("HISTORICAL ONLY · LAST STATUS ", self.html)
        self.assertIn("historical_only&&statuses.includes(x.previous_session_status)", self.html)
        self.assertIn("Historical setup details only; no current entry or live signal.", self.html)
        self.assertIn("All waiting stock setup details", self.html)
        self.assertIn("x.verified_levels", self.html)
        self.assertIn("x.last_completed_candle_time", self.html)
        self.assertIn("x.last_observed_minute_candle_time", self.html)
        self.assertIn("x.relative_volume_baseline", self.html)

    def test_closed_stock_setups_keep_historical_rank_but_clear_entry_plan(self):
        api = (pathlib.Path(__file__).resolve().parents[1] / "v2/backend/api.py").read_text(encoding="utf-8")
        setups = api[api.index('@app.get("/api/v2/stock-setups")'):api.index('@app.get("/api/v2/stock-setup-backtest")')]
        self.assertIn('row["previous_session_heuristic_rank_score"] = row.get("heuristic_rank_score")', setups)
        self.assertIn('row["historical_only"] = True', setups)
        self.assertIn('row["entry_reference"] = None', setups)
        self.assertIn('row["trade_plan"] = None', setups)
        self.assertIn('"last_completed_close": None', setups)
        self.assertIn('"verified_levels": []', setups)

    def test_stock_analysis_requires_scanner_rating_direction_agreement(self):
        self.assertIn("r.signal===rating.signal&&['BUY','SELL'].includes(r.signal)", self.html)

    def test_stock_detail_uses_fresh_stock_specific_rating(self):
        self.assertIn("String(x.symbol||'').toUpperCase()===symbol&&x.type==='STOCK'&&x.rating_basis==='CANDLE_ONLY_HEURISTIC'&&fresh(x)&&verifiedCandleScore(x)", self.html)
        self.assertIn("const live=Boolean(state.sessionOpen&&fresh(r)&&rating&&verifiedCandleScore(rating)&&r.signal===rating.signal", self.html)

    def test_stock_analysis_shows_historical_score_when_market_is_closed(self):
        self.assertIn("const historical=state.historicalRatings.find", self.html)
        self.assertIn("const score=live?rating:historical", self.html)
        self.assertIn("LAST STORED · HISTORICAL", self.html)
        self.assertIn("historical indicator heuristic", self.html)
        self.assertIn("This is the last stored indicator snapshot, not a current signal.", self.html)

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
        self.assertIn("x.exit_count+' recorded exits, gross '", self.html)
        self.assertIn("x.estimated_net_pnl", self.html)

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
        self.assertIn("const chargesFor=x=>", self.html)
        self.assertIn("table(['Stock','Entry','SELL exit','Gross P&L','Est. charges','Est. net']", self.html)
        self.assertIn("net=gross!=null&&cost!=null?gross-cost:null", self.html)
        self.assertIn('class="completed-positions-mobile"', self.html)
        self.assertIn("Estimated net P&amp;L", self.html)

    def test_pnl_history_returns_cost_adjusted_estimates_with_assumptions(self):
        api = (pathlib.Path(__file__).resolve().parents[1] / "v2/backend/api.py").read_text(encoding="utf-8")
        self.assertIn("AS estimated_costs", api)
        self.assertIn('"estimated_net_pnl": net', api)
        self.assertIn('"cost_estimate": {', api)
        self.assertIn("LEAST(20, buy_price * quantity * 0.001)", api)
        self.assertIn("0.00025", api)
        self.assertIn("0.0000307", api)
        self.assertIn("estimated_costs===null&&x.estimated_net_pnl===null", self.html)
        self.assertIn("estimated net after indicative charges", self.html)

    def test_index_scanner_and_rating_must_agree(self):
        self.assertIn("const sig=aligned?score.signal:'WAIT'", self.html)
        self.assertIn("aligned?'VERIFIED FRESH':'WAIT / UNVERIFIED'", self.html)

    def test_index_buy_sell_requires_fresh_scanner_row_as_well(self):
        self.assertIn("const aligned=Boolean(live&&score&&verifiedCandleScore(score)&&r?.signal===score.signal", self.html)
        self.assertIn("aligned?esc(score.rating)+'/100':'—'", self.html)

    def test_index_signals_require_fresh_verified_index_ratings(self):
        self.assertIn("x.type==='INDEX'&&x.rating_basis==='CANDLE_ONLY_HEURISTIC'&&fresh(x)", self.html)
        self.assertIn("WAIT / UNVERIFIED", self.html)

    def test_premarket_uses_upstox_global_context_when_market_is_closed(self):
        api = (pathlib.Path(__file__).resolve().parents[1] / "v2/backend/api.py").read_text(encoding="utf-8")
        self.assertIn('@app.get("/api/v2/premarket-data")', api)
        self.assertIn("global.json.gz", api)
        quote_client = (pathlib.Path(__file__).resolve().parents[1] / "v2/backend/upstox_quote_client.py").read_text(encoding="utf-8")
        self.assertIn("Full Market Quotes V3", quote_client)
        self.assertIn("Full Market Quotes V2", quote_client)
        self.assertIn("fetch_quote_groups", api)
        self.assertIn("GIFT NIFTY", self.html)
        self.assertIn("PRE-MARKET CUES UNAVAILABLE", self.html)
        self.assertIn("INDICATIVE PRE-MARKET · BULLISH", self.html)
        self.assertIn("No confidence percentage is invented", self.html)

    def test_premarket_labels_stale_upstox_quotes_but_keeps_last_values_visible(self):
        self.assertIn("const vixValue=Number(vix.value)", self.html)
        self.assertIn("HISTORICAL · no live reading", self.html)
        self.assertIn("LAST QUOTE · HISTORICAL", self.html)

    def test_premarket_shows_flow_report_date_and_marks_old_cash_data_stale(self):
        self.assertIn('id="pm-flow-status"', self.html)
        self.assertIn('id="pm-flow-data"', self.html)
        self.assertIn("Upstox daily NSE cash", self.html)
        self.assertIn("flow.fetched_at", self.html)
        self.assertIn("function renderPreFlows()", self.html)
        self.assertIn("STALE · HISTORICAL", self.html)
        self.assertIn("Not counted in the current-session reversal rule.", self.html)
        reversal = (pathlib.Path(__file__).resolve().parents[1] /
                    "v2/backend/reversal_context.py").read_text(encoding="utf-8")
        self.assertIn('flow.get("freshness") == "CURRENT"', reversal)
        self.assertIn('FLOW_FRESHNESS_DAYS = 4', reversal)

    def test_premarket_shows_daily_nifty_pe_with_date_and_last_stored_fallback(self):
        self.assertIn('id="pm-pe-card"', self.html)
        self.assertIn('id="pm-pe-value"', self.html)
        self.assertIn('id="pm-pe-status"', self.html)
        self.assertIn('id="pm-pe-detail"', self.html)
        self.assertIn("const peHasValue=Number.isFinite(Number(pe.value))&&Number(pe.value)>0", self.html)
        self.assertIn("LAST STORED · HISTORICAL", self.html)
        self.assertIn("session '+(pe.session_date||pe.as_of||'date unavailable')", self.html)
        reversal = (pathlib.Path(__file__).resolve().parents[1] /
                    "v2/backend/reversal_context.py").read_text(encoding="utf-8")
        self.assertIn('PE_DAILY_REFRESH_AFTER = clock_time(16, 0)', reversal)
        self.assertIn('save_daily_nifty_pe(new_record)', reversal)
        self.assertIn('FAILED_USING_LAST_STORED', reversal)
        archive = (pathlib.Path(__file__).resolve().parents[1] /
                   "v2/backend/nifty_pe_archive.py").read_text(encoding="utf-8")
        self.assertIn("CREATE TABLE IF NOT EXISTS daily_nifty_valuations", archive)
        self.assertIn("POSTGRESQL_AND_LOCAL", archive)

    def test_premarket_has_individual_color_bands_for_market_factors(self):
        self.assertIn('id="pm-factor-analysis"', self.html)
        self.assertIn('id="pm-factor-bands"', self.html)
        for label in ("NIFTY 50 P/E", "Crude & geopolitical news", "India VIX",
                      "FII / DII cash flows", "Observed volume"):
            self.assertIn(label, self.html)
        self.assertIn("Building baseline", self.html)
        self.assertIn("not confirmed market impact", self.html)
        self.assertIn("not NIFTY cash-index volume", self.html)
        self.assertIn("Historical · bullish stock RVOL", self.html)
        self.assertIn("role=\"img\" aria-label=", self.html)
        reversal = (pathlib.Path(__file__).resolve().parents[1] /
                    "v2/backend/reversal_context.py").read_text(encoding="utf-8")
        self.assertIn("read_nifty_pe_history(60)", reversal)

    def test_premarket_discloses_five_session_event_rules_without_probability(self):
        self.assertIn('id="pm-five-session-card"', self.html)
        self.assertIn("latest verified completed-session close within the next five trading sessions", self.html)
        self.assertIn("UP ONLY, DOWN ONLY, BOTH thresholds touched, or NEITHER", self.html)
        self.assertIn("not currently a trained ML forecast", self.html)
        self.assertIn("The five-session period is the separate forecast horizon, not the movement threshold.", self.html)
        reversal = (pathlib.Path(__file__).resolve().parents[1] /
                    "v2/backend/reversal_context.py").read_text(encoding="utf-8")
        self.assertIn('"five_session": {"event": event_spec(), **rule_definition()}', reversal)

    def test_premarket_discloses_medium_term_sustained_reversal_horizon(self):
        self.assertIn('id="pm-long-horizon-card"', self.html)
        self.assertIn("60 sessions", self.html)
        self.assertIn("10 of the final 15 session closes", self.html)
        self.assertIn("multi-year outlook would need a separate longer horizon", self.html)
        reversal = (pathlib.Path(__file__).resolve().parents[1] /
                    "v2/backend/reversal_context.py").read_text(encoding="utf-8")
        self.assertIn('"long_horizon_reversal": long_horizon_rule_definition()', reversal)

    def test_premarket_upstream_error_exposes_only_sanitized_machine_code(self):
        api = (pathlib.Path(__file__).resolve().parents[1] /
               "v2/backend/api.py").read_text(encoding="utf-8")
        self.assertIn('re.fullmatch(r"UDAPI\\d{3,6}", candidate_code)', api)
        self.assertIn('error["error_code"] = error_code', api)
        self.assertIn('error_code or "provider_code_unavailable"', api)
        self.assertNotIn('"message": first_error.get', api)

    def test_scorecard_hides_stale_candle_scores(self):
        self.assertIn("const validRating=x=>", self.html)
        self.assertIn("y.rating_basis==='CANDLE_ONLY_HEURISTIC'&&fresh(y)", self.html)
        self.assertIn("const score=x=>{const live=validRating(x),last=cached(x)", self.html)
        self.assertIn("Last '+Number(last.rating)+'/100 '+last.signal", self.html)
        self.assertIn("· historical", self.html)

    def test_market_data_refreshes_more_often_during_session_than_closed(self):
        self.assertIn("const delay=document.visibilityState==='visible'&&openNow()?10000:60000", self.html)
        self.assertIn("clearTimeout(refreshTimer)", self.html)
        self.assertIn("Date.now()-state.lastAuxLoadedAt>=60000", self.html)
        self.assertIn("state.lastHistoryLoadedAt<60000", self.html)

    def test_last_verified_score_cache_only_saves_fresh_aligned_scanner_ratings(self):
        self.assertIn("localStorage.getItem(SCORE_CACHE_KEY)", self.html)
        self.assertIn("!fresh(rating)||!fresh(row)||row.signal!==rating.signal", self.html)
        self.assertIn("localStorage.setItem(SCORE_CACHE_KEY,JSON.stringify(next))", self.html)
        self.assertIn("const counts={ALL:searched.length,BUY:searched.filter(x=>validRating(x)?.signal==='BUY')", self.html)
        self.assertIn("state.historicalRatings=Array.isArray(results[2].value.historical_ratings)?results[2].value.historical_ratings:[]", self.html)
        self.assertIn("rating.data_status==='HISTORICAL_LAST_STORED_CANDLE'", self.html)

    def test_quality_api_supplies_historical_scores_separately_from_live_ratings(self):
        api = (pathlib.Path(__file__).resolve().parents[1] / "v2/backend/api.py").read_text(encoding="utf-8")
        quality = api[api.index('@app.get("/api/v2/quality-ratings")'):]
        self.assertIn('"historical_ratings": []', quality)
        self.assertIn('"data_status": "HISTORICAL_LAST_STORED_CANDLE"', quality)
        self.assertIn('fresh = session_open and stamp.date() == now.date() and age <= timedelta(minutes=3)', quality)
        self.assertIn('timedelta(days=30)', quality)
        self.assertIn('"rating_basis": "HISTORICAL_INDICATOR_HEURISTIC" if historical', quality)
        self.assertIn('if e9 > e20 and mom > 0:', quality)
        self.assertIn('"directional_bias": "BULLISH" if bullish else "BEARISH" if bearish else "NEUTRAL"', quality)
        self.assertIn('const historical=x=>state.historicalRatings.find', self.html)
        self.assertIn('directional_bias||\'neutral\').toLowerCase()', self.html)

    def test_stock_setup_ranking_has_no_fixed_signal_cap(self):
        self.assertIn("/api/v2/stock-setups", self.html)
        self.assertIn("function renderStockSetups(hostId)", self.html)
        self.assertNotIn("state.stockSetups.*slice(0,10)", self.html)

    def test_stock_signals_require_live_verified_candle_rating(self):
        self.assertIn("const live=Boolean(state.sessionOpen&&fresh(r)&&rating&&verifiedCandleScore(rating)&&r.signal===rating.signal", self.html)
        self.assertIn("x.type==='STOCK'&&x.rating_basis==='CANDLE_ONLY_HEURISTIC'&&fresh(x)", self.html)
        self.assertIn("Ranked Stock Setups · All Qualifiers", self.html)

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

    def test_premarket_distinguishes_live_index_bias_from_partial_reversal_check(self):
        self.assertIn('id="pm-page-title">Market Context &amp; Direction</h1>', self.html)
        self.assertIn("live index bias uses index EMA and momentum only", self.html)
        self.assertIn("separate from the Trend Reversal rules check below", self.html)
        self.assertIn("LIVE INDEX BIAS", self.html)
        self.assertIn("unavailable?'NO DATA'", self.html)
        self.assertIn("No live signal is assigned", self.html)

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
            "/api/v2/top-momentum-setups": "https://nse-momentum-scanner-api.onrender.com/api/v2/top-momentum-setups",
            "/api/v2/top-volume-surge": "https://nse-momentum-scanner-api.onrender.com/api/v2/top-volume-surge",
            "/api/v2/stock-setups": "https://nse-momentum-scanner-api.onrender.com/api/v2/stock-setups",
            "/api/v2/stock-setup-backtest": "https://nse-momentum-scanner-api.onrender.com/api/v2/stock-setup-backtest",
            "/api/v2/nifty200-stock-board": "https://nse-momentum-scanner-api.onrender.com/api/v2/nifty200-stock-board",
            "/api/v2/quality-ratings": "https://nse-momentum-scanner-api.onrender.com/api/v2/quality-ratings",
            "/api/v2/nifty200-feed-health": "https://nse-momentum-scanner-api.onrender.com/api/v2/nifty200-feed-health",
            "/api/v2/experimental/15m-stock-screen": "https://nse-momentum-scanner-api.onrender.com/api/v2/experimental/15m-stock-screen",
            "/api/v2/experimental/15m-index-trends": "https://nse-momentum-scanner-api.onrender.com/api/v2/experimental/15m-index-trends",
            "/api/v2/trades": "https://nse-momentum-scanner-api.onrender.com/api/v2/trades",
            "/api/v2/preview-status": "https://nse-momentum-scanner-api.onrender.com/api/v2/nifty200-feed-health",
            "/api/v2/premarket-data": "https://nse-momentum-scanner-api.onrender.com/api/v2/premarket-data",
            "/api/v2/reversal-context": "https://nse-momentum-scanner-api.onrender.com/api/v2/reversal-context",
            "/api/v2/decision-learning": "https://nse-momentum-scanner-api.onrender.com/api/v2/decision-learning",
            "/api/v2/pnl-history": "https://nse-momentum-scanner-api.onrender.com/api/v2/pnl-history",
            "/api/v2/signal-activity": "https://nse-momentum-scanner-api.onrender.com/api/v2/signal-activity",
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
        self.assertIn(".mobile-nav{position:sticky;top:0;z-index:10;display:grid", self.html)
        self.assertIn(".mobile-nav button{width:100%;min-width:0;min-height:46px", self.html)

    def test_api_requests_time_out_instead_of_staying_on_loading_state(self):
        self.assertIn("new AbortController()", self.html)
        self.assertIn("async function get(path,timeoutMs=12000)", self.html)
        self.assertIn("setTimeout(()=>controller.abort(),timeoutMs)", self.html)
        self.assertIn("get(path,30000)", self.html)
        self.assertIn("finally{clearTimeout(timer)}", self.html)

    def test_reversal_context_refresh_updates_the_dedicated_flow_card(self):
        self.assertIn("function renderPreReversal(){\nrenderPreFlows();", self.html)

    def test_news_classifier_asset_has_a_matching_api_route(self):
        api_source = (HTML.parents[1] / "backend" / "api.py").read_text(encoding="utf-8")
        self.assertIn('<script src="./news_trend_relation.js"></script>', self.html)
        self.assertIn('@app.get("/news_trend_relation.js")', api_source)
        self.assertIn('v2/frontend/news_trend_relation.js', api_source)
        self.assertIn('media_type="application/javascript"', api_source)


    def test_nse200_board_explains_verified_session_change_and_keeps_all_stocks(self):
        for required in (
            'id="board-change-status"',
            "Ranked high to low by verified Upstox session change",
            "All 200 configured stocks remain listed",
            "change_status",
            "CURRENT','LAST_SESSION",
            ".sort(dailyChangeSort)",
            "All '+state.board.length+' stocks remain listed",
        ):
            self.assertIn(required, self.html)

    def test_nse200_mobile_rows_show_rank_change_price_and_quote_status(self):
        for required in (
            "stock-change-row",
            "Session change",
            "Previous close:",
            "Quote time unavailable",
            "const headers=['Rank','Favourite','Stock','Session change %'",
            "const changeCount=state.board.filter(hasVerifiedDailyChange).length",
        ):
            self.assertIn(required, self.html)

    def test_board_api_uses_read_only_upstox_quotes_for_change_percent(self):
        api = (HTML.parents[1] / "backend" / "api.py").read_text(encoding="utf-8")
        start = api.index('@app.get("/api/v2/nifty200-stock-board")')
        end = api.index("\n\n@app.get(", start)
        board = api[start:end]
        quotes = (HTML.parents[1] / "backend" / "nifty200_quotes.py").read_text(encoding="utf-8")
        for required in (
            "fetch_full_quotes(list(NIFTY_200.values()), tokens)",
            "quote_change_fields(symbol, NIFTY_200[symbol]",
            '"prev_close_price"',
            '"daily_change_pct": (price - previous_close) / previous_close * 100',
            '"stocks_with_change_data"',
            '"order_execution_enabled": False',
            "change_status",
        ):
            self.assertIn(required, board + quotes)


if __name__ == "__main__":
    unittest.main()

