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


## Restart preload indicator drift regression (2026-10-16)

`tests/test_offline_restart_preload.py` models the scanner's independent 60-completed-bar intraday startup preload and compares a resumed index history with an uninterrupted 375-minute same-session history. The tests require identical recent momentum and five-minute trend while preserving the expected EMA20 seed difference at restart. This isolates **preload-induced drift even when manager retention is unlimited**, rather than attributing every mismatch to an optional retention cap. The test also checks chronological selection and exclusion of the still-forming minute. It uses synthetic bars and the offline decision model only; it is not a historical market replay or proof of scanner end-to-end parity. Check CI at the latest commit for the result.


## Nine-case GitHub-hosted synthetic benchmark (2026-10-17)

Verified [Worker CI run 38948178483](https://github.com/rukminaiah-dot/nse-momentum-scanner/actions/runs/38948178483) succeeded at [e53677a](https://github.com/rukminaiah-dot/nse-momentum-scanner/commit/e53677a0703111a136255f0e51ad3a871558e916). Linux GitHub-hosted Python 3.11, 200 sequential snapshots and a separate 200-update contention pass per configuration. Each case runs in a fresh process. Times are milliseconds; RSS is peak process MiB. These measurements are synthetic and do not represent production/staging throughput or merge latency.

| Symbols | Bars/symbol | Snapshot p50 | Snapshot p95 | Snapshot p99 | Concurrent update p95 | Peak RSS MiB |
|---:|---:|---:|---:|---:|---:|---:|
| 50 | 60 | 0.1173 | 0.1275 | 0.1433 | 0.0031 | 13.98 |
| 200 | 60 | 0.1137 | 0.1404 | 0.1885 | 0.0032 | 16.69 |
| 500 | 60 | 0.1144 | 0.1239 | 0.1274 | 0.0030 | 22.47 |
| 50 | 390 | 0.7635 | 0.8158 | 0.9045 | 0.7863 | 20.31 |
| 200 | 390 | 0.7675 | 0.8149 | 0.8869 | 0.8101 | 37.72 |
| 500 | 390 | 0.7604 | 0.7955 | 0.8632 | 0.7990 | 74.56 |
| 50 | 1950 | 3.8269 | 4.1532 | 14.9851 | 3.9648 | 44.82 |
| 200 | 1950 | 3.8392 | 4.0100 | 4.1939 | 3.8445 | 136.70 |
| 500 | 1950 | 3.8351 | 3.9916 | 4.0816 | 3.9761 | 320.72 |

**Interpretation:** snapshot copying scales with per-symbol history length, while total retained memory scales with symbol count and history. The 50×1950 snapshot p99 outlier illustrates scheduler/runtime noise in a small 200-iteration sample. These results do not justify turning on a retention cap because correctness remains the primary blocker. Remaining performance gaps: dedicated recovery-merge latency distribution, measured lock-hold time, multi-worker contention, representative hardware and realistic feed rates.


## Synthetic recovery-merge latency results (2026-10-17)

[Worker CI 38948778930](https://github.com/rukminaiah-dot/nse-momentum-scanner/actions/runs/38948778930) passed all three recovery-merge benchmark cases at [69c34dd](https://github.com/rukminaiah-dot/nse-momentum-scanner/commit/69c34ddebb94231c85e2882a0509929ec827b48b). Each case uses 100 independent fresh managers, an active-minute boundary, idempotence checks and only same-session missing-minute candidates; prior-day retained history is not recovered.

| Preloaded history (minutes) | Missing recovered per merge | Merge p50 ms | Merge p95 ms | Merge p99 ms |
|---:|---:|---:|---:|---:|
| 60 | 6 | 0.0420 | 0.0507 | 0.0800 |
| 390 | 39 | 0.2818 | 0.3274 | 0.5252 |
| 1950 | 49 | 1.1127 | 1.1619 | 1.2722 |

The 1950-minute fixture spans calendar dates, but recovery candidates are confined to the active date. These numbers measure **single-threaded manager merge only** on GitHub-hosted Linux/Python 3.11, not broker latency, row verification, websocket scheduling, multi-worker contention, or production performance. They are not approval to enable a retention cap.


## Synthetic multi-thread contention results (2026-10-17)

[Worker CI 38950035431](https://github.com/rukminaiah-dot/nse-momentum-scanner/actions/runs/38950035431) passed both contention benchmark workloads at [e3be66d](https://github.com/rukminaiah-dot/nse-momentum-scanner/commit/e3be66dbc6d68062e9547700287f33fa47bc8c5a). All figures below are **end-to-end operation latency**, including scheduling and shared-lock waiting, on GitHub-hosted Linux/Python 3.11. They are not direct lock-hold measurements.

| Symbols | History/symbol | Threads | Operation | Samples | p50 ms | p95 ms | p99 ms |
|---:|---:|---:|---|---:|---:|---:|---:|
| 50 | 390 | 4 | Snapshot | 134 | 0.8065 | 0.8692 | 0.9514 |
| 50 | 390 | 4 | Update | 133 | 0.9623 | 2.0027 | 2.9215 |
| 50 | 390 | 4 | Empty merge | 133 | 0.1103 | 0.1471 | 0.8839 |
| 200 | 1950 | 8 | Snapshot | 267 | 4.0763 | 6.0253 | 72.6587 |
| 200 | 1950 | 8 | Update | 267 | 34.5611 | 103.4829 | 126.8856 |
| 200 | 1950 | 8 | Empty merge | 266 | 0.8003 | 0.8985 | 35.1848 |

**Performance risk / release gate:** the eight-thread, 1950-bar workload produced 103.48 ms update p95 and 126.89 ms update p99. The global manager lock and full-history snapshot copies may cause material tail latency under load. Do **not** treat a green CI run as performance acceptance. Require representative feed-rate and worker concurrency measurements, agreed latency thresholds and owner sign-off before merge or cap activation. The empty-merge operation does not model insertion of recovered bars, and this benchmark does not cover broker fetch, data verification or production scheduling. Keep the default retention cap disabled; short caps have already shown indicator drift in offline tests.
