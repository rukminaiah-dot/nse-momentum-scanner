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
