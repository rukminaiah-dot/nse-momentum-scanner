# 20-instrument APK candidate — not an approved release

0.9.0 uses a separate permanent package and an isolated debug package. See
[PHONE-SIGNING-SETUP.md](PHONE-SIGNING-SETUP.md) for phone-only private key setup.
No permanent key has been generated or provisioned by preparing this candidate.

Development branch only: experiment/android-paper-scanner. No production deployment.

## Implemented candidate

The existing favourites preference is now the active scan list (0–20 instruments).
No automatic stock selection or full-universe scan. Both manual and foreground
scans use that list; list changes are disabled during scanning. The NSE 200 catalog
remains available for selection, with NIFTY50, SENSEX and BANKNIFTY index entries.
Company-name/symbol search uses the official read-only Upstox instrument search
endpoint, with explicit NSE/BSE selection and pagination. The broker response
supplies the key; exchange tokens are never substituted for instrument keys.
NSE/BSE listings of the same company stay distinct. Add/remove is committed to
local preferences before the screen changes, and history is preserved on removal.
Search needs the token saved on-device. There is no new backend service.

Lookup accepts only consistent supported equity/index mappings. Unknown indices
and derivatives are omitted, malformed keys/pagination fail closed, and result
selections expire after five minutes. A successful lookup confirms the returned
identity, not intraday candle availability or profitable signals. That is checked
separately by the scan. Search failures never change the active list.

Equities retain 15-minute EMA20/50, Stochastic RSI and 20 verified same-slot volume
rules. Indices port the web experimental_15m_index_trend rule: 21 session-close
SMA, EMA20/50, Stoch RSI 14/14/3/3, body/edge and three-bar breakout; no index RVOL.
The Android calendar check verifies the actual exchange and exact preceding
sessions. Special sessions fail closed. Index history requests are split into
28-calendar-day windows. Candle caches use instrument keys to avoid symbol reuse.

This release uses completed 15-minute snapshots, not streaming live quotes.
There is no broker order endpoint. The web production implementation is unchanged.

## Release blockers

- Persistent private signing material has not been supplied. Debug builds are
  test artifacts only and must not be advertised as compatible updates.
- The original installed app's private signing key has not been recovered or
  proven available. Its certificate and package must be compared before update.
- Do not uninstall the existing app. If an original-key update is impossible,
  create a new stable package and migrate only data the old app can export.
- The in-app updater is implemented but a signed release channel has not been
  published. Debug builds refuse updates. Release builds require a newer version,
  matching package, SHA256, and the installed signing certificate before opening
  Android's confirmation. End-to-end real-device installation remains unverified.
- Live NSE/BSE/indices data, realme background behavior, backup/restore and two
  consecutive signed installations retaining data still require device tests.
- No profitability or historical performance is established by synthetic tests.

## Private signing activation (separate from production)

The manual android-private-candidate workflow uses an Android-only environment
`android-experimental-signing`. Its private secrets are ANDROID_KEYSTORE_BASE64,
ANDROID_SIGNING_STORE_PASSWORD, ANDROID_SIGNING_KEY_ALIAS and
ANDROID_SIGNING_KEY_PASSWORD. Provision the key through a private trusted system,
never through chat. Keep an encrypted offline recovery copy. The workflow never
publishes a release, deploys the server, or uploads private material. Its output is
a candidate for signature and update-preservation testing, not release approval.
The job verifies the public ANDROID_SIGNING_CERT_SHA256 environment variable.
The workflow runs on experimental pushes and explicitly skips signing when
configuration is absent; a successful status check alone is not a signed build.

Before enabling downloads in the app, retain one signing identity, use an HTTPS
release manifest with package/version/SHA256, verify package and signing certificate
against the installed app before invoking Android's installer, reject downgrades,
and require the user's installation confirmation. Publishing that channel needs
explicit approval. Google Play is not used for this stage.

## Update channel contract (not published)

A release tagged `android-paper-VERSION` must contain `android-update.json` with
`packageName`, numeric `versionCode`, HTTPS GitHub release `apkUrl`, and SHA256
`sha256`, plus the privately signed APK asset. Publishing requires explicit user
approval. The updater sends no Upstox token, rejects downgrades and foreign
packages/certificates, and leaves Android to ask the user to allow installation.
The current candidate does not create a release or publish update metadata.

## Test gates for 0.8.0 preview

The Android workflow runs the complete offline Python regression suite first,
then all Android unit tests, then packages the debug APK only if both pass.
Pure lookup/selection contract tests were committed and run before wiring the
network request. Additional tests cover encoded queries, exchange filters,
pagination, failed authentication, inconsistent responses, cancellation, redirect
rejection, local persistence, duplicate selection, the 20-item limit, and backup
round trips for BSE/index selections. Fixtures are synthetic; they do not establish
live broker access, live candle coverage or financial performance.

Official contract references:
- https://upstox.com/developer/api-documentation/instrument-search/
- https://upstox.com/developer/api-documentation/instruments/

## 0.10.0 index/stock separation

Home now has fixed Nifty 50 (NSE), Sensex (BSE) and Bank Nifty cards. They are
outside the 20 selected stock places and outside the RVOL ranking and stock
paper-outcome tables. Existing stock selections are retained. Legacy index
selections are treated as fixed Home indices, not as stock selections.

The index strategy retains EMA20/50, SMA of the previous 21 session closes,
Stochastic RSI 14/14/3/3, strong-body/edge and prior-three-bar breakout conditions.
There is no index RVOL requirement. The original web _paper_signal/evaluate_index
functions were compared with production and their rule logic is identical; no
production source was edited. Index reads verify the actual exchange calendar
and exact 21 preceding sessions. Historical requests use bounded 28-day windows.

Before the first completed current-session candle, on exchange-closed dates,
and after hours, the last verified session can supply clearly labelled historical
context. Historical and expired cached readings always display WAIT, never a live
BUY/SELL. Missing sessions, duplicate bars, missing completed candles and invalid
responses fail closed. Index snapshots persist separately and exclude credentials.
Manual Refresh index data is available on Home; full-day mode refreshes indices
and selected stocks separately. A token is still required inside app Settings.

CI validates fixtures, lifecycle/storage boundaries and build/signing checks.
Real Upstox index coverage, real-phone refresh and in-place update retention still
need device verification. No profitable signal or market-hours validation is implied.

Spot index candle parsing requires real validated OHLC but does not require a
volume field. The shared candle model carries an unused zero placeholder for
index volume; no index volume/RVOL is shown, ranked or interpreted. Equity
parsing still rejects absent/invalid volume. Regression tests cover both paths.


## 0.10.1 candidate: web index direction parity

Home index cards now use the existing Vercel scanner's `five_minute_trend` rule: three consecutive complete five-minute closes rise = BULLISH, fall = BEARISH, otherwise NEUTRAL. One-minute OHLC is fetched and aggregated only after completion; index volume is unused. Missing required minutes show WAIT; duplicate, future or malformed feed data fails closed. Saved 15-minute snapshots are invalidated through index snapshot schema version 2. Stock selections, token, paper history and stock strategy are unchanged. Index minutes never enter the stock candle cache.

Full-day service refreshes indices every five minutes, while deduplicating successful stock requests per 15-minute window and selection set. Historical sessions are explicitly labeled and never presented as live calls. Index close and daily percentage change use actual candle data; percentage is unavailable if the previous verified session close cannot be read.

Android tests cover rising/falling/equal/mixed closes, missing/duplicate/future minutes, independent NSE/BSE calendars, historical sessions, snapshot expiry, cancellation and safe error handling. On-device update and real broker parity remain pending; automated tests cannot establish trading accuracy.
