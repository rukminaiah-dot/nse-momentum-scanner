# Atomic candle-state prototype: review checklist

This draft PR is **not production-ready** and must not be deployed or merged solely because its offline tests pass.

## Verified in isolated tests

- Update, snapshot, and missing-only recovery insertion share the manager's lock.
- Recovery preserves live candles, refuses active/future minutes, rejects mismatched timestamps, and avoids invoking `update()`.
- Invalid batches are rejected before history is modified; duplicate-only batches do not replace the history list.
- History-limit accounting counts only retained recovered minutes.

## PR #7 worker adapter (draft-only; not connected)

The manager now exposes `merge_verified_recovery(key, recovered, snapshot_active_minute)` to match PR #7's `GapRecoveryWorker.merge` callback signature. The companion `snapshot(key)` already matches the worker's snapshot callback. Both acquire the manager's shared reentrant lock. The merge callback rejects missing, future, and cross-session snapshot boundaries; a delayed response from an earlier minute **within the same session** is allowed only for still-missing completed minutes strictly before the current active minute. Insertion is idempotent and never calls the live close/signal pipeline.

**Do not enable the worker yet.** PR #7 and PR #8 are separate branches. First assemble both in an isolated integration branch, test the actual worker against the actual manager with a fake broker response and deterministic races, and confirm the fetch callback only accesses approved read-only market-data endpoints. The worker's rate limits and market-session validation are additional safeguards, not substitutes for that integration test. Any production wiring or deployment requires separate explicit approval.

## Remaining integration blockers

- Audit modules **other than** `scanner.py` for direct reads and writes to `CandleManager.completed` or `current`. The scanner has been migrated on this draft branch, but the wider repository is not yet verified.
- Verify startup preload sequencing and failure handling under real scanner initialization; `preload_completed()` refuses replacement once a live candle starts.
- `snapshot()` now copies both the history list and its Candle objects; `preload_completed()` and recovery insertion also copy incoming candles. These are **detached mutable copies**, not frozen records. Validate the CPU/memory overhead for large NIFTY 200 workloads and verify that no consumer relies on object identity.
- Validate that recovered historical candles cannot trigger historical scanner results, BUY/SELL signals, or simulated trades.
- Define market-session reset and rollover semantics, and test cross-session recovery under concurrent updates.
- Decide how to preserve existing history beyond `limit` and whether the limit should apply to all history or only recovered minutes. Confirm against indicator warmup needs.
- The two lock-order tests now force recovery before and after live rollover. Still add sustained stress cases, cross-session rollover, and full scanner-level signal/trade side-effect validation.
- Only after these reviews, test an opt-in read-only staging integration with broker credentials and rate limits, then request explicit approval for any live rollout.

Related isolated recovery primitives: draft PR #7. Do not assume the two draft branches can be merged without resolving integration and conflict semantics.

## Scanner direct-access inventory (original main branch, now addressed in draft)

The following `v2/backend/scanner.py` locations **on the reviewed main revision** bypassed the prototype's lock:

- Line 195: `candles.completed[key] = loaded` (history preload **write**).
- Lines 73, 249, 486, 488, 515, 545, 550: direct `completed.get(...)` reads.
- Line 230: iteration over `candles.completed.items()`.
- Lines 518 and 525: direct indexing `candles.completed[key]`.

Line numbers refer to the reviewed main-branch revision and may shift. The preload write needs a separate synchronized initialization API or a guaranteed pre-concurrency startup phase. Snapshot-based readers must account for the mutable Candle objects and the fact that snapshots can become stale immediately after the lock is released. **Draft-branch status:** scanner history reads now use `snapshot()`, and preload writes use `preload_completed()`. Structural tests reject direct `candles.completed` access. The main branch remains unchanged.

## Critical signal-trigger coupling (original main branch, now addressed in draft)

The original main-branch `on_tick` path determined whether a candle closed by comparing
`len(candles.completed[key])` **before and after** `candles.update(...)`.
A recovery worker inserting historical candles concurrently can change that length,
causing the tick handler to call `analyse(key)` even when the tick did not close a
live candle. This defeats the intended guarantee that historical repairs do not
trigger signals, even though `insert_missing_completed()` never invokes
`update()` itself.

**Draft-branch status:** `on_tick()` now uses the return value of live `CandleManager.update()` (closed candle vs. `None`) as its close-event condition. An isolated runtime regression confirms that history growth alone does not trigger `analyse()`. A full scanner-level interleaving test, including trade/signal side effects, is **still required** before recovery is enabled.

