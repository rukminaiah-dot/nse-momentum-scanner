# Monday 19 October 2026 — Live Market Acceptance Checklist

**Scope:** Read-only observation of NSE Momentum Scanner. Do not merge PR #9, deploy, execute orders, mutate production databases, or enable retention as part of this checklist.

## Before market opens
- Confirm app is serving the expected branch only in a safe preview; production main is intentionally unchanged.
- Verify five pages: Dashboard, NSE 200 Scorecard, Stock Analysis, Pre-Market, Customization.
- Verify mobile navigation, dashboard section reordering, reset, and 20-favourite limit. Browser storage is device-specific.
- Confirm absent news, FII/DII, analyst, financial, RVOL and pivot feeds show **Not verified**, never synthetic figures.
- Confirm historical market data is labelled as stored, not live.

## During 09:15–15:30 IST
- Inspect Upstox connection, universe count, latest candle timestamp, feed health and stale-data suppression.
- Validate at least NIFTY 50, SENSEX and BANK NIFTY separately; ensure instrument IDs and index labels match.
- Compare completed 5-minute candle OHLC and candle close times against an independent source; do not treat preload as a live tick.
- Check Top 10 BUY-only candle-score ranking, including score tie ordering and candle freshness.
- Only enable/show Top 10 volume surge when observed comparative volume / RVOL and reference baseline exist.
- For a day-low recovery, compare actual intraday low, higher lows, bullish completed candles, volume and previous-day P/S1/S2/R1/R2. An intraday bounce is **not** a confirmed LONG.
- Reversal-event alerts must be emitted only for a verified state transition; test bearish→weakening→possible reversal→confirmed and failure paths without inventing historical transitions.
- Verify BUY→SELL history from persisted recorded entries/exits, with explicit signal-based P&L versus broker-confirmed P&L.
- Verify market closure resets live labels and does not display stale rankings as current.

## Release gates
- Independent decision parity and signal lifecycle parity evidence.
- Backend and browser/mobile smoke tests; no console errors.
- DB persistence/retention safety, performance acceptance, independent review.
- Explicit deployment approval after evidence is shared.

**Current known limitations:** live RVOL, global indices/FII/DII, company news, analyst ratings, financials, true reversal-event tracking, and durable automatic BUY→SELL capture are not verified/implemented. Never mark them complete solely from UI placeholders.


## 2026-10-19 live read-only verification (11:07 IST)

- Direct GET checks to the production Render API returned HTTP 200 for feed health, scanner results, the stock board, and quality ratings. Feed health reported market open, status `REPORTING`, and 200/200 NIFTY 200 symbols with a tick in the prior 120 seconds; order execution was `false`.
- The scanner returned 203 rows: the 200-stock universe plus NIFTY 50, BANK NIFTY, and SENSEX. All three index rows were timestamped 11:06 IST and within the frontend's three-minute freshness window at observation time. Index labels matched the expected three tracked instruments in the API response. This is label/shape verification, not independent quote-price verification.
- The stock board returned 196/200 fresh completed-candle rows. Four were correctly marked `HISTORICAL`: BLUESTARCO (11:01), BOSCHLTD (10:51), MRF (10:35), and PAGEIND (10:50). This can coexist with 200/200 recent ticks because feed tick freshness (120 seconds) and persisted scanner-candle freshness (three minutes) are separate measurements. The UI's live ranking paths require fresh board rows and aligned fresh ratings, so these four do not enter current signal rankings.
- The quality endpoint returned five ratings in `RESEARCH_ONLY` mode; all use the `CANDLE_ONLY_HEURISTIC` basis, have `volume_verified=false`, and report order execution disabled. This does not verify RVOL, liquidity, independent signal accuracy, or justify an order.
- The connection report's last recorded event was `CONNECTED` at 09:52:03 IST. The endpoint itself cautions that a last event is not a continuous-connection guarantee; the fresh-tick counts are the current coverage evidence.
- The UI health panel now shows tick coverage separately from fresh completed-candle coverage and names each window. Five-page UI contract test added for those labels and the stale-row exclusion explanation.
- Verification boundary: Vercel's protected preview redirected this environment to login, so the deployed Vercel proxy/browser rendering could not be independently smoke-tested here. Official independent live index-price comparison and full broker/Upstox payload audit were not completed; the public search result available during this session was stale. No broker credentials or order routes were accessed, and no production code, database, deployment setting, or orders were changed.


### 11:11 IST recheck

- Repeated the read-only API checks in parallel. Feed health remained `REPORTING` with 200/200 recent ticks; the stock board reported 195/200 fresh completed candles. The change from 196 to 195 confirms the per-minute coverage number is live and time-dependent.
- All eight quality ratings in this sample matched a scanner row with the same candle timestamp and signal. Stock ratings also matched a `LIVE_FRESH` board row. All were `RESEARCH_ONLY`, candle-heuristic scores, and order execution remained disabled.
- This confirms response-shape and freshness alignment for the sampled rows only. Independent exchange quote validation and Vercel browser-route verification remain outstanding.
