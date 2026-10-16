# Fix 10: isolated Upstox websocket acceptance gate

Status: **LIVE ACCEPTANCE NOT YET VERIFIED**. This is a release checklist, not evidence of passing integration. Offline feature CI has not been confirmed passing at the latest commit.

## Preconditions
- Run only in a disposable **nonproduction** service/process; do not change the production Render service or its environment.
- Use a dedicated, short-lived Upstox credential in a secret store. Never commit, print, or paste the token in logs or chat.
- Keep `ENABLE_VERIFIED_GAP_RECOVERY` disabled in production and PR #5 draft.
- No order-placement functions, trading endpoints, or auto-trading process may run.
- Select one authorized liquid instrument and conduct the check during an NSE trading session.
- Stop if the token lacks required market-data access, if market is closed, or if websocket authorization fails. A read-only historical API success is not a websocket success.

## Isolated live harness result semantics
- The tick-only smoke mode uses `FIX10_LIVE_STREAM_ACK=READ_ONLY_STREAM_TEST` and verifies a fresh instrument tick entered `CandleManager`; it does **not** verify recovery.
- Recovery mode additionally requires `FIX10_ISOLATED_RECOVERY_ACK=READ_ONLY_HISTORY`. Without controlled-gap acknowledgement, a historical request is scheduled only after a same-session live minute jump.
- Explicit `FIX10_CONTROLLED_GAP_ACK=BROKER_BACKED_MEMORY_ONLY` runs a **separately labelled controlled acceptance** after a genuine fresh websocket tick. It reads actual broker historical candles, seeds all available eligible completed minutes except one in isolated memory, then uses the off-feed worker to fetch and insert exactly the omitted broker minute. No synthetic websocket ticks or broker candles are generated.
- Exit code `0` in natural-gap recovery mode requires at least one verified historical insertion. In explicitly controlled-gap mode, it requires **exactly one** verified insertion and an intact active minute. These are different evidence categories: controlled acceptance is **not** proof of a naturally occurring websocket gap. Exit code `3` means inconclusive; exit code `2` means blocked preflight/initialization.
- Do not force a fabricated market tick into the live websocket to obtain a green result. The deterministic synthetic-gap scenario belongs in offline integration tests; real-market evidence must be labelled separately.

## One-run manual workflow (feature branch only)
- The feature-branch `.github/workflows/manual-upstox-probe.yml` combines offline tests, authenticated read-only historical validation and isolated websocket recovery in that order. **Do not trigger it until final review and authorization.**
- Supply an authorized `instrument_key` and a short-lived repository Actions secret `UPSTOX_ACCESS_TOKEN`; never paste credentials into workflow inputs.
- The job explicitly sets `ENABLE_VERIFIED_GAP_RECOVERY=false` and runs only on `feature/verified-gap-recovery`. No orders, scanner process, or production deploy is invoked.
- The consolidated workflow now selects the controlled broker-backed gap mode to make a single run useful even when no natural gap occurs. It still requires fresh live websocket data and authenticated history. A naturally occurring live gap remains a separate acceptance item, and a controlled pass must not be described as proof of it.
- GitHub may require a manual-dispatch workflow file to exist on the default branch before it appears in the Actions UI. **Do not change `main` merely to expose this workflow**; resolve visibility and deployment implications separately before asking for the one manual trigger.

## Nonproduction acceptance sequence
1. Start an isolated process subscribing to the Upstox market-data websocket with a **read-only** instrument subscription. Confirm live ticks arrive with exchange timestamps.
2. Record only redacted diagnostics: tick count, candle-minute count, connection state, recovery attempt count, insertion count, errors. Do not log token, raw ticks, OHLCV, or order data.
3. Feed real ticks into an isolated `CandleManager`; verify minutes never move backwards on late/out-of-order ticks.
4. During an active session, introduce a missing **completed** minute in isolated memory only; trigger `GapRecoveryWorker` off the websocket callback thread. Do not manufacture a missing broker candle.
5. Confirm the authenticated read-only intraday endpoint returns validated same-day completed candles; verify exactly the missing minute is inserted when available, existing completed candles are unchanged, and the active minute is untouched.
6. Repeat the request: expect zero additional insertions (idempotence).
7. Delay the historical response while real websocket ticks continue; verify ticks are not blocked and a newly advanced active minute remains intact.
8. Simulate a historical API exception and malformed candle in isolation; confirm no merge, pending slot release, and no order activity.
9. Confirm global request spacing, per-instrument cooldown and pending cap in logs/metrics; stop on any broker throttle or reconnect storm.
10. Shut down the isolated process; ensure no production configuration or data was changed.

## Evidence required before rollout discussion
- CI passing at the exact feature commit used for the live test.
- Nonproduction service/process identity, commit SHA, date/session, and redacted test output for steps 1–10.
- Evidence that the websocket callback is not blocked by recovery and shared locking protects state.
- Explicit sign-off on Upstox rate limits and market-session handling.
- A separate, reversible rollout/rollback plan. **Do not merge or enable the feature merely because the historical API probe passed.**

## Controlled acceptance state hygiene
- A successful controlled check removes both broker-backed seed anchors and the single recovered test candle from the live-feed manager. The active live candle must remain unchanged.
- A completed negative check (for example, inconsistent broker OHLCV) must also remove controlled historical candles. If a historical worker is still pending at the bounded timeout, acceptance is inconclusive and cleanup does **not** race the worker; the disposable isolated process must terminate rather than reuse that state.
- Controlled evidence requires exactly one worker request, one completed worker and one retained verified insertion, with no earlier worker activity. A separate natural-gap event cannot share the controlled acceptance counters.
- GitHub Vercel status alone does not establish Python offline CI results; verify the exact feature commit's Python workflow before manual acceptance.
