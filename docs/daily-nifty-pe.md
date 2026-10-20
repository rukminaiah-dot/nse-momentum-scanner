# Daily NIFTY 50 P/E display

The Pre-Market page shows NIFTY 50 P/E as a **daily end-of-day context value**.
The backend checks NSE's index snapshot after 16:00 IST on weekdays; it does not
poll for a live intraday valuation. The session date returned by NSE is kept
separate from the fetch time.

Successful values are stored by session date in Render PostgreSQL when
`DATABASE_URL` is configured, and in the scanner SQLite database as a local
fallback. If the daily refresh is blocked or fails, the UI keeps the latest
stored P/E and labels it `LAST STORED · HISTORICAL`, with its session date and
refresh status. An absent reading stays unavailable; the app does not derive
P/E from price or substitute another provider.

P/E is descriptive context only. A single P/E value is not a buy/sell or
reversal trigger. No cheap/expensive label is inferred without a consistent
historical earnings basis and comparison range.
