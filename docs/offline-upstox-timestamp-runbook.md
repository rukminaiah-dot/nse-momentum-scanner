# Offline Upstox V3 timestamp diagnostic runbook

**Scope:** offline decoded samples only. No feed connection, production access,
scanner hooks, trading orders, database writes, or deployment.

## What can be established

The diagnostic distinguishes three independent clocks:
- `ltpc.ltt`: broker-reported last-trade timestamp;
- `currentTs`: broker-reported feed-envelope timestamp;
- `arrival_ms`: local receipt timestamp supplied by the caller.

`trade_status=STALE` with `envelope_status=FRESH` is consistent with a
recently delivered snapshot containing an old last trade. It is not by itself
evidence of an Upstox defect, nor proof of an exchange session classification.

`regular_hours_window` is **time-of-day only**. It does not account for
holidays, special sessions, closing auctions, or the verified NSE calendar.
`session=UNKNOWN` remains the only valid session interpretation.

## Safe offline invocation

Use locally constructed synthetic decoded dictionaries, or separately
authorized, sanitized nonproduction samples. Never commit credentials, tokens,
instrument keys, prices, raw payloads, or personally identifying data.

```python
from v2.backend.upstox_timestamp_extraction import summarize_decoded_messages

samples = [
    ({"currentTs": 1792060080000,
      "feeds": {"REDACTED": {"ltpc": {"ltt": 1792058280000}}}},
     1792060080000),
]
print(summarize_decoded_messages(samples))
```

The example values are **illustrative** and do not represent observed NSE
trades. The output is a list of count-only timing categories; do not publish
per-message timing records unless separately reviewed.

## Nonproduction real-feed acceptance checklist

1. Obtain explicit authorization and isolated nonproduction credentials before
   opening a real feed. No existing production access token reuse.
2. Confirm actual decoded V3 payload paths for `ltpc.ltt` and `currentTs`
   and whether the first message is a snapshot.
3. Capture local receipt time immediately on message receipt; ensure the
   machine clock is synchronized and record any measured clock uncertainty.
4. Compare morning open, 15:29–15:30, closing-auction, post-close, reconnect,
   and next-session samples without retaining sensitive payload data.
5. Validate session boundaries against dated official NSE capital-market
   circulars and amendments. Resolve published timing discrepancies first.
6. Keep the scanner session gate disabled until independent review and explicit
   authorization for any integration or production change.

**Interpretation rule:** neither a fresh envelope nor a post-15:30 last-trade
timestamp alone establishes that an ordinary continuous-session candle should
be updated.
