# Atomic candle-state prototype: review checklist

This draft PR is **not production-ready** and must not be deployed or merged solely because its offline tests pass.

## Verified in isolated tests

- Update, snapshot, and missing-only recovery insertion share the manager's lock.
- Recovery preserves live candles, refuses active/future minutes, rejects mismatched timestamps, and avoids invoking `update()`.
- Invalid batches are rejected before history is modified; duplicate-only batches do not replace the history list.
- History-limit accounting counts only retained recovered minutes.

## Outstanding blockers

- `scanner.py` and other modules read `CandleManager.completed` directly. These readers do **not** acquire the new lock. Review and migrate reads to snapshots or another consistent access contract before enabling concurrent recovery.
- Audit all direct writes to `completed` (including preloading) and `current`; route them through synchronized manager methods or establish an explicit startup-only invariant.
- `snapshot()` copies the history list, **not the mutable Candle objects**. The live active candle remains mutable. Readers requiring immutable OHLCV snapshots need separate copies or a defined lock discipline.
- Validate that recovered historical candles cannot trigger historical scanner results, BUY/SELL signals, or simulated trades.
- Define market-session reset and rollover semantics, and test cross-session recovery under concurrent updates.
- Decide how to preserve existing history beyond `limit` and whether the limit should apply to all history or only recovered minutes. Confirm against indicator warmup needs.
- Add deterministic multithreaded tests that exercise real `CandleManager.update()` racing with insertion, not just a simulated callback lock.
- Only after these reviews, test an opt-in read-only staging integration with broker credentials and rate limits, then request explicit approval for any live rollout.

Related isolated recovery primitives: draft PR #7. Do not assume the two draft branches can be merged without resolving integration and conflict semantics.

## Scanner direct-access inventory (main branch review)

The following `v2/backend/scanner.py` locations currently bypass the prototype's lock:

- Line 195: `candles.completed[key] = loaded` (history preload **write**).
- Lines 73, 249, 486, 488, 515, 545, 550: direct `completed.get(...)` reads.
- Line 230: iteration over `candles.completed.items()`.
- Lines 518 and 525: direct indexing `candles.completed[key]`.

Line numbers refer to the reviewed main-branch revision and may shift. The preload write needs a separate synchronized initialization API or a guaranteed pre-concurrency startup phase. Snapshot-based readers must account for the mutable Candle objects and the fact that snapshots can become stale immediately after the lock is released. These call sites are **not changed** by this prototype.

## Critical signal-trigger coupling (scanner lines 486-493)

The live `on_tick` path currently determines whether a candle closed by comparing
`len(candles.completed[key])` **before and after** `candles.update(...)`.
A recovery worker inserting historical candles concurrently can change that length,
causing the tick handler to call `analyse(key)` even when the tick did not close a
live candle. This defeats the intended guarantee that historical repairs do not
trigger signals, even though `insert_missing_completed()` never invokes
`update()` itself.

**Required before integration:** use the actual return value of the live
`CandleManager.update()` call (closed candle vs. `None`) as the close-event
condition, rather than history-length changes. Test a recovery insertion
interleaved with a same-minute tick and assert no analysis/trading signal fires.
Do not wire recovery into the scanner until this is addressed.

