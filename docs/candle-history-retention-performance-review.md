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

## Retention parity acceptance gate (offline design)

The current nine retention regression tests passed in [CI run 38940672810](https://github.com/rukminaiah-dot/nse-momentum-scanner/actions/runs/38940672810) at `ad0223f`, including three synthetic EMA regimes and capped recovery. These tests establish invariants, **not** an acceptable production retention size.

Before activating a cap, replay a representative, timestamped historical dataset in two isolated candle managers: one unlimited and one capped. At each eligible completed minute, compare EMA9, EMA20, ATR14, momentum, 5-minute trend, RVOL and the final BUY/SELL/HOLD decision with identical inputs. Record maximum and p95 absolute/relative EMA drift, decision disagreement count, warmup and restart behavior, and whether any difference changes a BUY or SELL action. The acceptance thresholds must be explicitly approved before testing; do not choose a threshold after inspecting outcomes. A **zero unexplained BUY/SELL disagreement** is a conservative proposed release gate, not evidence that any cap meets it.

Include gap-recovery inserts, missing minutes, session transitions, and restart preloads. Replay must remain credential-free, order-disabled and isolated from production databases. Until such evidence exists, keep `max_completed_per_symbol=None` and the PR in draft.

## Scanner-level replay implementation boundary (2026-10-16)

Source review of `v2/backend/scanner.py` identifies why invoking the scanner directly is **not** an acceptable offline parity harness: after calculating a signal it calls `save_scan_result(...)`, and for a qualifying stock BUY it calls `buy(...)` and `load_active_trades()`. An offline replay must never reach these paths.

A safe next implementation should extract the *pure decision calculation* into a separate function that accepts a supplied completed-candle history, instrument classification (index versus stock), and the market-regime input. It should return the computed indicators, trend, continuity block reason, and final signal without importing scanner startup, accessing a database, using network clients, or placing orders. The production call path must not be switched to that function until parity against existing behavior is established with unit tests and explicit review.

Scanner logic to preserve in the pure model:

- Require at least 20 completed bars, and for index calculations use only bars from the current IST session.
- Require the latest six bars to be consecutive one-minute candles from today's IST session; otherwise block the signal entirely.
- Compute EMA9/EMA20, momentum, ATR14, and stock RVOL using the exact current implementations and windows.
- Build 5-minute trend from **complete** five-candle buckets, using only the latest session and three complete buckets; gate stock BUY/SELL on BULLISH/BEARISH respectively.
- Apply index-specific EMA/momentum directional override and stock-only ATR late-entry rejection; preserve current market-regime treatment.
- Compare not only BUY/SELL/HOLD but also continuity blocks, intermediate indicators, and rejection reasons. Report results by instrument class and price regime.

Current synthetic core parity compares only `generate_signal` and must not be represented as complete scanner parity. At `58e1037`, a 60-bar cap produced HOLD→BUY and HOLD→SELL divergences in adversarial histories; those cases are now protected by tests at `da4d300`. Keep all caps disabled.

## CI negative controls and approval interpretation (2026-10-16)

The isolated scanner decision comparison now distinguishes primary index, secondary index, and stock paths. In the four synthetic price regimes at 400 bars, each retention limit is compared across 4,560 instrument/prefix combinations. The 60-bar candidate produced four index-class disagreements (HOLD→BUY and HOLD→SELL in both index classes); 200 bars produced zero in this limited dataset. The comparison is run from the offline worker workflow. `tests/test_offline_scanner_retention_probe.py` asserts the precise 60-bar negative-control set and the current 200-bar baseline so future edits cannot silently remove those cases.

**Important:** the 200-bar zero-disagreement assertion is a regression baseline, **not** a safety approval threshold. Additional realistic or adversarial datasets are expected to expand the coverage and may reveal 200-bar differences. The replay uses synthetic timestamps beyond normal market-session length, a separate calculation implementation, and no actual scanner startup. None of these findings justify a production or staging cap change. Any decision to enable retention requires a reviewed historical-data replay, independently checked scanner-rule equivalence, and explicit deployment authorization.

## Offline phase exit checklist (2026-10-16)

- [x] Keep retention opt-in and disabled by default; no live scanner configuration change.
- [x] Exercise preload, closed-candle append, and recovery merge retention paths with offline unit tests.
- [x] Exercise indicator, core signal, and isolated scanner-model comparisons at 60 and 200 bars.
- [x] Preserve known 60-bar HOLD→BUY and HOLD→SELL index counterexamples as CI negative controls.
- [x] Exercise primary/secondary index and stock classifications, session warmup, overnight continuity, missing minutes, and complete five-minute buckets.
- [x] Test 375-minute previous-session boundaries at both caps.
- [ ] Independently verify the isolated scanner model against production scanner logic without executing scanner startup, DB writes, or broker/order paths.
- [ ] Replay representative licensed historical market sessions, including gaps, reversals, and session rollover; inspect not only final signal but intermediate indicator and rejection diagnostics.
- [ ] Establish reviewed signal-parity acceptance thresholds and memory/latency tradeoffs from the historical replay.
- [ ] Obtain explicit deployment authorization before activating any cap.

**Disposition:** offline unit/synthetic-validation phase is complete only when the latest branch-head CI has passed. The 60-bar cap has demonstrated signal changes and is not an acceptable transparent replacement. The 200-bar candidate remains research-only. This checklist is not permission to deploy, merge, change broker settings, or access production data.

## Read-only scanner-rule inspection (2026-10-16)

Inspected `v2/backend/scanner.py` as **source text only**, without importing or executing its module. The current isolated `offline_signal_parity.py` reproduces the inspected index-specific 20-current-session-bar warmup, six consecutive same-day one-minute candles, EMA9/EMA20 and five-bar momentum, stock RVOL from the latest 20 volumes, inherited NIFTY 50 regime for secondary indices and NIFTY 200 stocks, three complete five-minute trend buckets, index directional override, and ATR late-entry checks. This is a **manual source-rule correspondence review**, not an independent runtime equivalence test. The scanner's real-time clock, symbol mappings, persistence, scanner startup, and order side effects are intentionally outside the offline model.

**Distinct preload limit:** `scanner.py` currently selects `current[-60:]` for its same-session intraday preload before calling `candles.preload_completed`. That existing **preload selection** is separate from `CandleManager(max_completed_per_symbol=60)`, which is still not activated. A live startup can therefore begin with fewer candles than the offline synthetic unlimited-history reference even without a manager retention cap. Historical replay must model actual preload and warmup behavior rather than interpreting the offline negative controls as proof that live scanner history is always unlimited.


## Scanner five-minute trend source-level parity gate (2026-10-16)

`tests/test_scanner_trend_source_parity.py` parses the actual `scanner.py` source and compiles only its top-level `five_minute_trend` function under restricted builtins. The scanner module itself is **never imported or initialized**. A small call/syntax allowlist makes the test fail closed if the extracted function grows unsafe dependencies. Synthetic same-session, overnight, partial-bucket, flat, rising, falling, and reversed-input cases are compared directly against the independent offline model. This is a meaningful **source-level** equivalence check for the five-minute trend helper, not equivalence of the entire scanner decision path, API preload, or order-execution gates. It does not substitute for licensed historical replay or deployment approval. CI evidence must be checked at the commit containing this test before marking it passed.
