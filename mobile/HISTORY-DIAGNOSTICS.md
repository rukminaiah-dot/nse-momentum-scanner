# Investigating missing candle history

Reproduce a failed scan, then open Settings → Diagnostics → Export diagnostic log.
Save `nse-diagnostic-log.txt` and attach it to the support conversation. Copy diagnostic
summary is also available, but the exported file preserves more history.

Log timestamps are UTC. Candle dates and `slots` use Asia/Kolkata; each slot is
the candle's start time in HHmm (for example, 0915 means 09:15 IST).

- `HISTORY_FETCH`: symbol, requested date range, received candle count, elapsed
  milliseconds, or an allowlisted failure code. RECEIVED only means the request
  returned; subsequent validation determines whether history is usable.
- `HISTORY_DAY`: date, expected/received/missing/extra counts, invalid and duplicate
  counts. FETCHED, CACHE and RETRY identify the source; BLOCKED shows unresolved data.
- `HISTORY_MISSING`: every missing candle start time for that date and symbol.
- `HISTORY_RETRY`: started, complete, incomplete, safe error code, or
  SKIPPED_DAY_LIMIT when more than two sessions need repair.
- `HISTORY_RECOVERY`: verified cached-day count and remaining incomplete sessions.
- `SCAN_BLOCKED` / `REVERSAL_HISTORY`: the reason the row remains unavailable.

Example (illustrative, not a live Upstox observation):

```text
HISTORY_MISSING FETCHED date=2026-11-03 slots=0915,0930 symbol=TCS
HISTORY_RETRY INCOMPLETE date=2026-11-03 symbol=TCS
HISTORY_MISSING BLOCKED date=2026-11-03 slots=0915,0930 symbol=TCS
```

Logs retain the existing seven-day rotation and daily size bound. They exclude
tokens, request URLs, instrument keys, response bodies and raw exception messages.
Export soon after reproducing the failure because older entries can rotate out.
Recovery validation, retry limits and trading/exit rules are unchanged.
