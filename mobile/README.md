# Android paper scanner prototype

This isolated Android app is in the experimental branch. It does not replace or call the production scanner.

## Current prototype

- Native Android UI with Home, NSE 200, Favourites, and Settings tabs.
- Search all 200 configured NSE symbols and save up to 20 favourites on-device.
- Paper-only scan uses Upstox 15-minute V3 candle endpoints in read-only mode.
- Local SQLite cache stores candles; duplicate, invalid, incomplete, stale, and insufficient-baseline data are rejected or shown as WAIT/unavailable.
- Requires the same 15-minute slot from exactly 20 exchange-verified prior regular sessions for RVOL.
- Volume-first screen applies to all 200; EMA 20/50 and Stochastic RSI confirmation runs only for saved favourites.
- Access token is encrypted with Android Keystore-backed AES-GCM and never written to logs or sent anywhere except Upstox API requests.
- No order endpoint, real trading, or production integration.

## Token setup

Generate a personal access token from Upstox Developer Apps and enter it in the app Settings screen. The app secret is not embedded in the APK. If Upstox rejects or expires the token, the app reports an authentication error and scanning must wait until a fresh token is entered. Never send the token to ChatGPT or place it in source control.

## Current limitations

- This is an experimental debug build, not a Play Store release.
- Live market validation still requires installing the APK on an Android device and running a read-only scan with the user's own token.
- Android must allow the scan to remain active while a scan is in progress. The user starts each scan; there is no unattended background scheduler.
- Upstox, internet availability, and correct instrument keys remain dependencies. No profitability claim is made.

## Build and test

From this directory, use Gradle 8.9, JDK 17, and Android SDK platform 35:

```sh
gradle :app:testDebugUnitTest :app:assembleDebug
```

The GitHub Actions workflow runs unit tests and creates a debug APK artifact on the experimental branch.

## Session verification and scan controls (0.2.0)

- Fetches date-specific `/v2/market/timings/YYYY-MM-DD` responses, walking back until exactly 20 prior NSE sessions are known (maximum 60 calendar days). A successful response without NSE marks a closed date. Calendar failures stop the scan. No weekday-only inference.
- Supports regular 09:15–15:30 IST sessions, including a weekend session if the API explicitly reports those hours. Special/short sessions stop the scan with an explicit unsupported-session message; they are never silently replaced by older sessions.
- Requires all 25 unique, valid 15-minute bars for every one of those 20 sessions. The same-slot average uses exactly those dates. Missing bars or sessions remain unavailable, even when older cached dates exist.
- Fetches history in nonoverlapping ranges of at most 28 calendar days. Missing history can be retried in the same day. Cached full sessions avoid unnecessary history calls; today's bars must come from the fresh intraday response.
- All stocks use the same last completed slot fixed when the scan starts. The current session must contain every completed slot up to that point. Forming bars are excluded, and late scans more than 3 minutes after market close are rejected.
- Up to 4 stocks run concurrently. All HTTP attempts share a 200 ms pacing gate (up to 5 starts/second); at most 3 attempts, 25-second total timeout per attempt, 10-minute overall scan deadline. 429 uses a shared cooldown (numeric Retry-After, bounded to 60 seconds; otherwise 2 seconds). Network failures and 5xx retry with backoff; authentication failures stop the scan. Other use of the same Upstox account can still consume its rate allowance.
- Cancel scan cancels outstanding calls and backoff waits. Cancellation, timeouts, failed scans, and new scans discard the previous report. Snapshots expire after 15 minutes. Keep the app in the foreground; leaving the activity may cancel the scan.
- Favourites show candle OHLCV, EMA 20/50, and Stochastic RSI (14,14,3,3). Indicators use the verified history rather than restarting at an arbitrary 52-bar slice. BUY/SELL remain experimental paper labels, require all strategy filters, and otherwise show WAIT. No position tracking or HOLD inference.
- Home lists all volume-qualified stocks in descending RVOL order. Settings shows safe reason counts; symbol rows identify failures without exposing tokens or API response bodies. `failedRequests` is retained as a report field name but counts affected stocks, not individual HTTP attempts.

Calendar schema, live instrument-key validity, actual throttling, and full 200-stock data coverage still require a read-only phone/API test. Unit fixtures are synthetic correctness tests, not backtest or profitability results. No historical performance evaluation is implied.
