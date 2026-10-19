# Verified candle recovery integration contract (not enabled)

This branch supplies **offline-tested primitives only**. It does not connect recovery to the live scanner or authorize broker orders.

Before any live integration:

1. Use the existing websocket candle-state lock for **both** the worker's `snapshot(key)` and `merge(key, recovered, active_minute)` callbacks. Do not hold this lock during broker HTTP requests or worker sleeps.
2. Re-read the **current** active minute under that lock when merging. The minute returned by `snapshot` is only a historical boundary and may be stale by the time the broker responds. Never insert the active or future minute.
3. Insert only verified **missing** completed minutes for the current IST session. Preserve live candles unchanged. Re-run continuity checks rather than fabricating gap data or retroactively emitting trading signals.
4. Keep recovery opt-in and fail closed on invalid rows, network errors, rate limits, empty history, or unavailable authentication. The worker is not a websocket callback and must not delay that callback.
5. Bound request rate, pending work, history length, and logging. Do not log broker credentials or sensitive response bodies.
6. Test with broker read-only responses in an isolated environment first. The manual intraday probe verifies **current-day** minutes only; historical missing minutes need an appropriate historical endpoint and separate validation.
7. Require review of lock ordering, stale snapshots, market session changes, and downstream signal behavior before enabling recovery on any live service.

CI: `python -m unittest discover -s tests -p 'test_minimal_verified_recovery.py' -v`.

## Findings from current `main` code review (2026-10-16)

- `v2/backend/candle_manager.py` has mutable `current` and `completed` dictionaries, but **no shared lock**. Its `update()` appends a just-closed candle on minute rollover and ignores older ticks. Any background recovery merge must synchronize with this update path.
- `v2/backend/scanner.py` accesses `candles.completed` directly for quality reporting, analysis, and signal persistence. Integration therefore requires a deliberate lock boundary for readers as well as writers, or immutable per-symbol snapshots; adding a lock only inside the recovery worker is insufficient.
- A safe minimal design is to add a per-symbol lock (or one bounded global lock) at the candle-manager ownership layer, expose atomic snapshot and insert-missing-completed operations, and re-evaluate the live active minute inside the insertion critical section.
- Recovery insertion must be a **data-quality repair only**. Do not invoke the scanner's normal candle-closed signal pipeline or retroactively persist trading signals. Future live closures can use repaired history after normal continuity checks.
- Add race tests that interleave live minute rollover with recovery insertion, and tests proving that repaired candles do not generate historical BUY/SELL events, before proposing production wiring.
