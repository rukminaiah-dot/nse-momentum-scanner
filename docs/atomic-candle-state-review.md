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
