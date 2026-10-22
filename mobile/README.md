# Android paper scanner prototype

This isolated Android app is in the experimental branch. It does not replace or call the production scanner.

## Current prototype

- Native Android UI with Home, NSE 200, Favourites, and Settings tabs.
- Search all 200 configured NSE symbols and save up to 20 favourites on-device.
- Paper-only scan uses Upstox 15-minute V3 candle endpoints in read-only mode.
- Local SQLite cache stores candles; duplicate, invalid, incomplete, stale, and insufficient-baseline data are rejected or shown as WAIT/unavailable.
- Requires exactly 20 previous weekday observations at the same 15-minute slot for RVOL.
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
