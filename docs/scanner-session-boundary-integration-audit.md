# Offline scanner session-boundary integration audit

**Review scope:** static source review of `v2/backend/scanner.py`,
`v2/backend/session_guard.py`, and `v2/backend/candle_manager.py`.
No feed connection, runtime instrumentation, production configuration change,
or release approval. Findings describe the feature branch at review time.

## Current processing sequence

`scanner.on_tick(key, data)` extracts `ltp` and `ltt`, performs a
two-minute freshness check against the local wall clock, optionally evaluates
the weekday-only stock session gate, rejects out-of-order ticks, then updates
feed-health, simulated trade state, cumulative volume, and candles. On candle
closure it may request gap recovery and run signal analysis.

## Release-blocking gaps

1. **Calendar integration is absent.** The scanner's opt-in
   `ENABLE_NSE_SESSION_CANDLE_GATE` calls `session_tick_action`, a
   weekday/time-only classifier. It does not call the separate
   `accepted_calendar_tick_action` helper. Do not enable the flag.
2. **Indices bypass the optional stock gate.** The condition is restricted to
   `key in NIFTY_200.values()`; index candles and index analysis use the
   ordinary update path even if the flag is enabled. A production rollout
   would need an explicit, reviewed policy for index instruments.
3. **No timer-driven finalization.** The verified-calendar finalizer exists
   only as an explicitly called helper; `on_tick` does not invoke it. The
   final 15:29 candle may remain active if no subsequent valid tick arrives.
4. **Weekday gate has no close grace.** `session_tick_action` can return
   `FINALIZE_LAST_MINUTE` for a same-day 15:29 candle at 15:55, whereas the
   verified-calendar classifier defaults to a five-minute grace window.
   The weekday gate is not a substitute for the verified classifier.
5. **Timestamp interpretation remains unproven.** `on_tick` treats
   `ltt` as event time, without correlating Upstox `currentTs` and
   receipt time. Freshness alone cannot classify closing-auction or
   snapshot semantics.
6. **Feed-health semantics require explicit review.** The early return on
   rejected stock ticks occurs before `record_feed_health`, which measures
   accepted ticks rather than all received messages. Any change must
   preserve separately defined received-feed and accepted-trade metrics.

## Required offline integration acceptance matrix

| Case | Required behavior |
| --- | --- |
| Verified regular-session stock tick | Update permitted candle only |
| Verified regular-session index tick | Apply separately approved index policy |
| Missing/expired/unverified calendar | Fail closed; no signal, volume, trade, or accepted-tick mutation |
| Explicit closed date | No trading-state mutation |
| Explicit special/early-close date | Honor the exact dated calendar boundary |
| Delayed snapshot or out-of-order `ltt` | Do not roll candle backward or create a false after-hours bar |
| Final minute with no subsequent trade | Finalize once using separately authorized scheduler/clock |
| Repeated close, restart, prior-day candle | No duplicate or cross-session finalization |
| Reconnect and feed outage | Distinguish received messages from accepted trades and candle health |

## Release decision

**Blocked.** A static review does not establish real-feed behavior.
Before any production integration: obtain dated authoritative NSE calendar
evidence, isolate and observe real V3 timestamps under separate authorization,
agree on stock/index and health semantics, implement a fail-closed calendar
integration with offline tests, and request explicit approval for merge/deploy.

The current task does **not** authorize live Upstox access or any production
action.
