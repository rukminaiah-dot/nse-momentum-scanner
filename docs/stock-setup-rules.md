# NSE 200 stock setup rules

The scanner is a read-only research display. It does not create simulated positions or place broker orders. It evaluates the 200 configured symbols and returns every current setup without a daily signal cap.

## Data checks

- Setup and trigger candles are completed five-minute bars aggregated from verified one-minute candles. The current forming candle is excluded.
- A stale candle, missing five-minute interval, invalid OHLC, or absent verified level produces `WAIT` with a reason.
- Previous-day high and low are accepted only when the fetched prior session contains all 375 consecutive one-minute bars from 09:15 through 15:29 IST.
- Opening range high and low use the first three complete five-minute bars, 09:15–09:30 IST.
- No locally calculated or proxy VWAP is used.
- RVOL is the latest completed five-minute volume divided by the average volume for that same slot across 20 prior sessions. Fewer than 20 valid prior-session observations makes RVOL unavailable and blocks directional triggers.

## Setup and confirmation

- `WATCH`: price is within the configured approach distance of a verified level, recent completed bars contract in range, and their volume eases.
- `TRIGGERED`: the six completed bars before the breakout show configured range contraction and easing volume near the same verified resistance/support; then a completed five-minute candle closes through that level, its body is at least 50% of range, its close is within the outer 25% in the breakout direction, and verified same-slot RVOL meets the threshold. The breakout candle itself is excluded from the compression calculation.
- `CONFIRMED`: the next completed candle holds the level. The entry reference is its close; the stop is beyond that candle's structure with the configured buffer.
- `INVALID`: price closes back through the trigger level, breaches the confirmed stop, or the cost-adjusted target plan fails. A new setup requires invalidation or a new compression watch.

EMA 9 and EMA 20 are shown as context only. Ranking points are deterministic heuristic ordering scores, never probabilities.

## Trade-plan estimates

The display shows 1% and 2% target references and marks each viable only when no other verified opposing level lies between entry and target and the indicative net reward-to-risk clears the configured minimum. Estimated charges are an indicative round-trip schedule per one share based on the app's existing fee assumptions; actual charges depend on executed quantity and account tariff. Slippage is shown as unavailable because historical spread/quote data is not stored. No signal is confirmed if both targets fail the cost/risk checks.

## Configurable environment variables

- `SCANNER_MIN_5M_RVOL` (default `1.5`)
- `SCANNER_LEVEL_APPROACH_PCT` (default `0.15`)
- `SCANNER_COMPRESSION_BARS` (default `3`)
- `SCANNER_COMPRESSION_RANGE_RATIO` (default `0.85`)
- `SCANNER_COMPRESSION_VOLUME_RATIO` (default `0.85`)
- `SCANNER_MIN_NET_REWARD_RISK` (default `1.5`)
- `SCANNER_5M_MAX_AGE_MINUTES` (default `7`)
- `SCANNER_STOP_BUFFER_PCT` (default `0.01`)

## Backtest status

The service currently retains scanner summaries, not point-in-time multi-year five-minute OHLCV and level snapshots. It also lacks historical spread/slippage observations and trade quantity/account tariff records. Therefore the complete rules have not been backtested; expectancy, win rate, average win/loss, drawdown, signal count, and regime results are withheld. Do not treat live heuristic ranking as tested performance.
