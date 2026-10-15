# Experimental NSE session gate — acceptance checklist

**Status:** Offline-only development on draft PR #5. Do not enable the production flag or merge without explicit approval.

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
