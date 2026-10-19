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

## Additional official-source finding: post-15:30 activity

NSE's equities timings page distinguishes the **normal/odd-lot market close at 15:30 IST** from closing-auction and closing-session activity. The current NSE holidays/timings resource describes closing-auction order matching 15:30–15:35 and a transition period 15:35–15:50, followed by a closing session 15:50–16:00. A separate NSE market-timings page describes a closing session starting at 15:40. **The two published pages differ**, so obtain the applicable dated circulars and product/segment details before treating either timeline as a verified per-day calendar.

Upstox's CAS market-data announcement (effective September 4, 2026) confirms that V3 WebSocket feeds can carry closing-auction values. An after-15:30 event may be legitimate exchange activity but must not automatically update normal continuous-session candles.

Sources:
- https://www.nseindia.com/resources/exchange-communication-holidays
- https://www.nseindia.com/static/market-data/market-timings
- https://upstox.com/developer/api-documentation/announcements/market-quote-v3-full-quotes/

**Required observer extension before real-feed use:** separately capture envelope `currentTs`, `ltpc.ltt`, local message-receipt time, and the relevant market-status/CAS fields; retain only redacted timing and status metadata. The current offline helper accepts only `ltt` and arrival time, and cannot establish which exchange session produced an event.
