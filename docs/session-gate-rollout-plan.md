# NSE session gate: observation-first rollout plan

**Status: proposal only. No production changes authorized.** Follow [session-gate-acceptance.md](session-gate-acceptance.md) before proceeding.

## Phase 0 — authoritative inputs (release blocked)

1. Obtain official NSE equity session/holiday circulars for the proposed operating date range, including special sessions and early closes. Record URLs, retrieval date, dates covered, and reviewer.
2. Build a complete date-to-session schedule with explicit closed dates. Reject missing or expired coverage. `verified=True` is a caller acknowledgment, not evidence of authenticity.
3. Confirm the Upstox V3 timestamp field represents exchange event time, with actual payload samples; do not infer this from candle log times alone.
4. Resolve the weekday-only classifier currently wired behind `ENABLE_NSE_SESSION_CANDLE_GATE`. **Do not enable this flag** while it ignores official exchange calendars.

## Phase 1 — offline integration

- Wire a verified, bounded calendar into a separately reviewed scanner implementation, not into production directly.
- Test ordinary open and close, holiday rejection, weekend special-session acceptance, early close, late ticks, next-day restart, stale active candle, and duplicate finalization.
- Assert that rejected ticks cannot affect trade state, OHLCV, feed-health, cumulative volume, or signal generation; valid ticks must continue to work.
- Retain an explicit fail-closed policy for missing calendar dates and unverified sources.

## Phase 2 — observation only

- Run a non-production observer on real Upstox ticks with no order placement and no production state writes.
- Compare raw exchange timestamps, arrival times, candidate session decisions, and candle-close events, particularly around 15:29–15:55 IST.
- Validate NIFTY 200 coverage, feed reconnection, missing-minute recovery, and the last-minute candle across multiple sessions, including an exchange holiday/special session when available.
- Archive redacted traces and reviewer sign-off. Do not treat green CI as real-feed evidence.

## Phase 3 — approval and controlled activation

- Request explicit approval for any merge, deploy, or production flag change.
- Before an approved rollout, capture a known-good revision and the existing flag state. Establish rollback owner and monitoring window.
- Monitor accepted/rejected tick counts, candle-close timestamps, signal counts, coverage, and errors. Abort on unexpected rejection of valid ticks, after-hours signals, missing stock coverage, or feed degradation.
- Rollback requires separate explicit authorization for production action: restore the prior known-good revision/configuration and verify behavior from logs.

**Current status:** The scanner uses a weekday-only gate; the verified-calendar helpers are offline-only. No authoritative calendar, real-feed acceptance evidence, production approval, or live rollout is claimed.
