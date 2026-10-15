# Experimental NSE session gate — acceptance checklist

**Status:** Offline-only development on draft PR #5. Do not enable the production flag or merge without explicit approval.

## Hard release blockers

1. **Do not enable the weekday-only scanner gate in production.** It does not consult official NSE holidays or special trading sessions, and could reject valid weekend/special-session ticks or accept holiday ticks.
2. **Do not treat the explicit-calendar helpers as integrated.** They remain offline-only until a verified exchange calendar and reviewed scanner/candle-manager wiring are supplied.
3. **Do not equate green CI with real-feed acceptance.** Actual Upstox tick-time evidence and session-boundary observation are still required.
4. **Do not silently lose the last candle when no closing tick arrives.** The current tick-driven finalization only closes an active 15:29 candle when an eligible later tick arrives; the next day's first tick safely discards stale state, but cannot reconstruct that missing close. Design and test an authorized, idempotent end-of-session finalization or verified historical reconciliation, including process downtime and restart. Do not add a speculative live timer.

## Evidence required before rollout

- [ ] Independently verify NSE equity trading dates and session hours against official exchange circulars, including holidays, special sessions, early closes, and unscheduled changes. Record source URLs, retrieval time, covered dates, and reviewer.
- [ ] Confirm a complete date-by-date schedule for the intended deployment window. Closed dates must be explicitly marked closed; missing dates fail closed.
- [ ] Integrate the verified schedule with the scanner and candle manager in a separate reviewed change. The current verified-calendar helpers are **not** connected to live scanner processing.
- [ ] Run offline integration tests for 09:15 open, normal in-session ticks, 15:29/15:30 close, delayed post-close ticks, overnight/weekend ticks, and a verified special-session/early-close case.
- [ ] Verify real Upstox V3 tick timestamp semantics (event time vs arrival time) and reconcile observed 15:50–15:55 IST candle logs with raw tick evidence. Do not assume cause.
- [ ] In a non-production or observation-only environment, record actual WebSocket traces around the session boundary. Verify candle OHLCV, idempotent finalization, trade-state isolation, feed-health behavior, and signal suppression outside authorized hours.
- [ ] Confirm NIFTY 200 coverage, reconnection, stale-feed handling, and missing-minute recovery do not regress.
- [ ] Verify recovery from a process restart during/after close and during the next market open.
- [ ] Obtain explicit approval before merge, production deploy, or enabling `ENABLE_NSE_SESSION_CANDLE_GATE`. Document rollback procedure.

## Known limitations

The existing `regular_session_minute` and `session_tick_action` functions check weekday clock hours only, **not** official exchange holidays or special sessions. The newer explicit-calendar helpers are pure offline functions; their `verified=True` argument is an acknowledgment, **not cryptographic proof of provenance**. No live-feed acceptance evidence has been collected for these changes. Passing offline CI is necessary but not sufficient for production readiness.
