# Calendar-aware scanner integration: offline implementation design

Status: **design only; not authorized for live wiring or deployment**.
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

## Required integration tests before any wiring

- Exercise the **real `on_tick` function** with AST-isolated fake dependencies
  (the existing `test_scanner_session_execution.py` pattern), not only the
  independent policy/dispatch helper.
- Assert no accepted timestamp, trade update, health write, volume baseline,
  candle, recovery request, or signal changes for a rejected stock **and**
  rejected index event.
- Test explicit exchange closed dates, early closes, weekend special sessions,
  date-range expiry, invalid calendar provenance, malformed timestamps,
  out-of-order events, and repeated finalization.
- Check the live disabled-by-default path remains behaviorally unchanged.
- Keep the offline isolation guard in place until a separately reviewed,
  explicitly authorized integration replaces it.

## Rollout blockers

- No authenticated, complete NSE dated session calendar has been supplied.
- No isolated real Upstox V3 timestamp observation has been authorized.
- No stock/index feed-health semantics or clock-finalization design has been
  approved.
- Production enablement, deployment, merge, or live feed access is not
  authorized.

**Decision:** continue offline tests and review only; do not enable the
weekday-only `ENABLE_NSE_SESSION_CANDLE_GATE` flag.
