# Verified gap recovery: staging activation checklist

Status: **draft and not deployed**. Production remains disabled unless an operator deliberately configures both flags.

## Controlled staging enablement

On an isolated staging scanner with synthetic or approved read-only broker credentials, explicitly configure:

```sh
NSE_RECOVERY_MODE=staging
NSE_ENABLE_VERIFIED_GAP_RECOVERY=1
```

Both flags are required; missing, differently cased, or partial values disable the worker. Do **not** add these settings to production. This PR does not deploy or change any Render environment variables.

## Validation sequence

1. Confirm startup logs say `VERIFIED_GAP_RECOVERY: ENABLED_STAGING` only in staging; verify `DISABLED` without both flags.
2. Confirm historical preload completes before the worker is configured. Inject a synthetic same-session gap and verify the worker requests only the missing completed minute(s), never the active minute.
3. Validate actual Upstox intraday payload shape and timezone in read-only staging; reject malformed, duplicate, future, cross-session and off-session rows.
4. Observe rate limits, worker failures, cooldown, and feed responsiveness during normal and burst ticks. Recovery must not cause a trade or a scanner analysis event by itself.
5. Exercise disconnect and shutdown with a pending worker; confirm bounded wait and that no stale snapshot overwrites the active candle.
6. Verify unchanged production startup and no broker order placement. Obtain explicit approval before merge or deployment.

## Known limits

The offline tests cannot establish broker endpoint compatibility, market-hours behavior, peak RSS, or real websocket latency. The worker does not automatically rescan gaps already followed by contiguous candles; only gaps observed at a live rollover trigger requests. The five-second shutdown wait is bounded, not cancellation of an in-flight network request. These are staging review items, not production-readiness claims.
