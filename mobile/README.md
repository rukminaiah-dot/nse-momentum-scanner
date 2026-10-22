# Android paper scanner prototype

This is an isolated Android app in the experimental branch. It does not replace or call the production scanner.

## Current prototype

- Native Android UI with Home, NSE 200, Favourites, and Data Health tabs.
- Search across the configured 200 symbols and save up to 20 favourites on-device.
- Keeps unknown or missing market data visibly unavailable; no sample prices or fabricated signals.
- Paper-only strategy core for completed 15-minute candles, 20-session same-slot volume, EMA 20/50, and Stochastic RSI confirmation.
- No order API, broker order calls, or trading execution.

## Current limitation

The read-only Upstox login and candle fetch are not connected yet. Until they are implemented and validated, the app correctly shows WAIT / DATA NOT VERIFIED. Do not use it for live market decisions.

## Build and test

From this directory, use Gradle 8.9 with JDK 17 and Android SDK platform 35:

```sh
gradle :app:testDebugUnitTest :app:assembleDebug
```

The GitHub Actions workflow runs unit tests and creates a debug APK artifact for the experimental branch.
