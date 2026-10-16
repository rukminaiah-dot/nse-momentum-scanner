# Candle history retention and snapshot performance review

Status: design note only; no production configuration or deployment changes.

## Retention invariant

The recovery `limit` is a **per-batch cap on newly accepted missing minutes**, not a maximum length for completed history. Recovery must never evict candles previously created by live ticks or startup preload, because those candles may still be needed for indicator warmup. A successful merge may increase total history length; it does not trigger pruning. Tests exercise both long-history preservation and recovery batch limiting.

**Outstanding bound:** `CandleManager.update()` appends one closed minute indefinitely, and `preload_completed()` accepts arbitrary history. Thus the current prototype has no total-memory bound. A bounded design needs a separately named `max_completed_candles` policy, configured above the longest required indicator lookback plus warmup margin, applied at a safe lifecycle boundary and tested for restart consistency. Do not silently reuse the recovery batch limit for retention.

## Snapshot cost and measurement

`snapshot(key)` holds a per-manager `RLock` while shallow-copying every completed `Candle`, then returns a detached list and active-minute key. For `N` completed candles, each call is O(N) in time and allocation, and briefly blocks live tick updates and worker merges. For `S` symbols sampled at frequency `F`, copying work scales approximately with `S × F × N`. This is a complexity estimate, **not** a measured throughput claim.

Before staging: benchmark 50/200/500 symbols with representative histories (60/390/1950 candles), concurrent update and snapshot traffic, and report p50/p95/p99 lock hold and update latency plus peak RSS. Run on hardware representative of staging; record Python version, host CPU, memory, test duration, symbol distribution and workload. Do not infer production readiness from offline correctness tests alone.

## Release gates

- Determine longest scanner indicator lookback and preload depth, then agree on explicit retention and restart semantics.
- Ensure snapshot copying does not starve websocket tick ingestion during NIFTY200 bursts.
- Audit remaining direct reads of `completed` and `current` in all consumers before wiring the recovery worker.
- Validate market-session boundaries and reconnect/replay sequencing in approved read-only staging.
- Keep draft PRs unmerged until review; no production deploy, real broker orders, or safety-check bypass.

## Opt-in bounded prototype and indicator parity (2026-10-16)

The draft branch now supports `CandleManager(max_completed_per_symbol=N)` for a positive integer N. The default is `None` (unbounded), and the scanner does **not** pass a cap. When opted in, preload, live closure and missing-history recovery retain the most recent N completed candles; the active minute is separate. Offline tests cover Friday-to-Monday rollover and prevent an older recovery candidate from displacing the newest history.

**Important signal-parity blocker:** `indicators.ema(values, period)` initializes from `values[0]` and iterates over **all** retained values, not merely `period` bars. Even a cap of 60, while above the scanner's minimum 20-bar warmup and 20-bar RVOL window, can change EMA9/EMA20 values and downstream signal decisions versus unlimited history. A regression test explicitly demonstrates the difference. The scanner also computes ATR14, five-minute trend from same-session candles, five-bar momentum with six-minute continuity, and RVOL from 20 volumes. A cap must not be selected on nominal indicator periods alone.

**Decision:** Leave the cap disabled in every deployed and broker-connected environment. Before selecting a value, define acceptable EMA drift and signal-parity thresholds, test representative historical price regimes and restarts, and verify whether persistent indicator state or an explicitly defined warmup horizon is required. No safe numeric staging cap is approved by this note.
