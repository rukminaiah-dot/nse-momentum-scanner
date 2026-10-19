# Calendar-aware scanner integration: offline implementation design

Status: **offline feature-branch integration implemented and CI-tested; not authorized for live feed wiring or deployment**. The explicit `on_tick_with_verified_calendar(...)` entrypoint in `v2/backend/scanner.py` delegates to the existing scanner tick handler only after a calendar decision. The `UpstoxLiveV3(on_tick=on_tick)` startup callback is unchanged.
This document complements `scanner-session-boundary-integration-audit.md`.

## Separation of responsibilities

1. **Decode and validate timestamps.** Distinguish exchange trade time
   (`ltpc.ltt`), feed envelope time (`currentTs`), and local receipt time.
   The live scanner currently only receives `ltt`; the meaning of observed
   post-close traffic remains unverified.
2. **Resolve the session calendar.** Require explicit coverage for the IST
   date and a separately verified exchange source. Missing dates, malformed
   boundaries, expired coverage, and unverified provenance must fail closed.
   A source label and caller-supplied `verified=True` are acknowledgements,
   not independent proof.
3. **Classify before side effects.** The same decision must apply to stock
   and index keys. A `REJECT` result must occur before accepted-tick health,
   simulated trade updates, cumulative volume, candles, recovery requests,
   or signal generation.
4. **Separate finalization from tick ingestion.** `FINALIZE_LAST_MINUTE`
   may close an existing final-minute candle once, without treating the
   triggering post-close tick as a trade. A separately designed clock-driven
   finalizer is needed when no further feed event arrives. It must not
   infer a missing bar or finalize a prior session.
5. **Make feed health explicit.** Track raw receipt and accepted-trade
   activity separately; a session rejection is not proof of an outage.

## Offline integration verification and remaining test work

- **Implemented and CI-tested:** AST-isolated real `on_tick` execution and explicit calendar entrypoint with synthetic stock/index ticks (`test_scanner_session_execution.py`).
- Assert no accepted timestamp, trade update, health write, volume baseline,
  candle, recovery request, or signal changes for a rejected stock **and**
  rejected index event.
- Test explicit exchange closed dates, early closes, weekend special sessions,
  date-range expiry, invalid calendar provenance, malformed timestamps,
  out-of-order events, and repeated finalization.
- Check the live disabled-by-default path remains behaviorally unchanged.
- **Implemented and CI-tested:** AST guard asserts live startup remains on the legacy `on_tick` callback; calendar entrypoint is not feed-wired.
- **Still required:** exhaustive side-effect assertions for indices and stocks across all exceptional timestamp/calendar conditions, independent calendar provenance verification, and no-tick clock-finalization design.

## Rollout blockers

- No authenticated, complete NSE dated session calendar has been supplied.
- No isolated real Upstox V3 timestamp observation has been authorized.
- No stock/index feed-health semantics or clock-finalization design has been
  approved.
- Production enablement, deployment, merge, or live feed access is not
  authorized.

## Tomorrow's controlled test readiness

- **Ready now:** synthetic offline stock/index calendar-gating and finalization tests; both feature-branch CI workflows passed on commit `fb8a3ca` (270 offline tests and 105 WebSocket preflight tests).
- **Manual input needed for realistic tests:** independently authenticated, complete NSE dated calendar covering the test date(s); authorized isolated Upstox V3 timestamp samples and explicit permission before any real feed connection.
- **Not ready:** production or live-feed tests, unattended no-tick close handling, and deployment. Do not treat a green synthetic suite as proof of live-market correctness.

**Decision:** continue offline review only; do not enable the weekday-only `ENABLE_NSE_SESSION_CANDLE_GATE` flag or replace the live Upstox callback without separate approval.
