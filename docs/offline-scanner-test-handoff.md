# Offline scanner handoff for controlled testing

**Scope:** feature branch `feature/verified-gap-recovery` / PR #5. This is an
offline-only handoff. The test calendar is synthetic and **not** official NSE
calendar evidence. Do not connect Upstox, deploy, trade, enable production
flags, or merge based solely on the green test results.

## How to reproduce without a broker

From the checked-out feature branch in a local Python 3.11 environment:

```sh
python -m compileall -q v2/backend
python -m unittest discover -s tests -p 'test_scanner_session_execution.py' -v
python -m unittest discover -s tests -p 'test_verified_session_finalization.py' -v
python -m unittest discover -s tests -p 'test_offline_scanner_session_policy.py' -v
python -m unittest discover -s tests -p 'test_offline_scanner_session_dispatch.py' -v
```

The GitHub Actions workflow `.github/workflows/verified-gap-recovery.yml`
runs the broader recovery, scanner, and calendar test suite on branch pushes.
The separate WebSocket Preflight workflow checks its own offline regressions.

## Acceptance checks

| Scenario | Required result |
| --- | --- |
| Valid stock or index synthetic session tick | Calendar entrypoint allows UPDATE; real scanner handler runs with fake dependencies |
| Missing, nonnumeric, nonfinite, zero, or negative tick price | REJECT before any candle, trade, volume, or feed-health side effect |
| Stale, future, or out-of-order exchange timestamp | REJECT before any scanner mutation; wrapper must not report a false UPDATE |
| Concurrent tick and clock-driven finalization | Serialized against candle manager lock; finalized candle cannot reopen |
| Unverified, incomplete, closed-day or expired date calendar | REJECT; no scanner health, volume, trade or candle mutation |
| Last-minute candle with first close-boundary tick | FINALIZE_LAST_MINUTE exactly once, no new close-minute candle |
| Last-minute candle with no post-close feed event | Explicit `finalize_verified_calendar_without_tick` can close it once within grace |
| Late or duplicate last-minute tick after verified finalization | REJECT at scanner calendar entrypoint; cannot reopen last minute or change accepted state |
| After close-grace expiry | No finalization |
| First legitimate tick of a later date | Candle manager accepts the new date normally and clears its previous finalization watermark |
| Existing production callback | `UpstoxLiveV3(on_tick=on_tick)` unchanged; new entrypoints **not** live-wired |

## Remaining manual gates before a real-feed test

1. Authenticate a complete, dated NSE session calendar that covers every
   test date, explicitly including holidays and any special/short sessions.
   A source string plus `verified=True` is only an acknowledgement, not
   authentication.
2. Authorize and inspect isolated Upstox V3 timestamp observations, including
   exchange `ltt`, envelope `currentTs`, and local receive time.
3. Approve a separate reviewed wiring and scheduling plan for live ticks and
   no-tick close behavior, with clear raw-versus-accepted feed-health rules.
4. Explicitly approve any subsequent deployment, merge, or trading behavior.

**Not done:** autonomous time-based scheduling and live data integration.
The new no-tick finalizer is an explicit callable; no timer is running.
