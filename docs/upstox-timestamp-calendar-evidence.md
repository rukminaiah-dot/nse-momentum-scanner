# Upstox V3 timestamp and NSE calendar evidence (2026-10-15)

**Research only — no production activation or calendar enforcement.**

## Upstox documented fields

- V3 feed documentation calls `ltpc.ltt` **last traded time**, with examples containing 13-digit Unix-epoch millisecond timestamps. Do not interpret it as the WebSocket message arrival time.
- The envelope `currentTs` is distinct from `ltpc.ltt`. Capture this broker-supplied timestamp *and* an independently captured local receipt time when a separate, authorized nonproduction feed observer is available.
- V3 sends a market-data snapshot after connection; a fresh arrival may carry an older last-trade timestamp.
- Newer V3 documentation also describes pre-open and closing auction information. A post-15:30 feed event is not automatically proof of an ordinary continuous-session trade.

Source: https://upstox.com/developer/api-documentation/v3/get-market-data-feed/

## NSE official source (equities, 2026)

The NSE equities holiday listing includes **15 January 2026** (Maharashtra municipal election), in addition to holidays appearing in the original annual calendars. Do not substitute F&O, currency-derivative, or *settlement* holiday lists for the equities trading calendar.

The NSE listing also notes **8 November 2026** Muhurat trading, with timings to be notified separately. Do not assume ordinary hours on that Sunday.

Source: https://www.nseindia.com/resources/exchange-communication-holidays

## Acceptance blockers

1. Obtain dated NSE capital-market circulars and amendments, including any special sessions, and independently review dates and session hours for the proposed coverage period.
2. Build an explicit, versioned, bounded calendar that fails closed on missing dates. A web listing alone is not a fully verified operating calendar.
3. Observe `ltpc.ltt`, envelope `currentTs`, and local receipt time side by side in a **separate nonproduction process**, without logging credentials, instruments, prices or raw payloads.
4. Test reconnection snapshots and events at 09:15, 15:29–15:30 and after 15:30. Do not treat a fresh post-close message as a valid continuous-session tick.
5. Review results before wiring the calendar into scanner processing. Leave `ENABLE_NSE_SESSION_CANDLE_GATE` disabled until approval and verification.

**Production logs from 2026-10-15 are not sufficient to establish whether Upstox supplied post-close `ltt` values.**
