# PR #9 — Historical replay acquisition and authorization

Status: **not executed; waiting for authorized historical data**. This is a handoff procedure, not replay evidence or approval.

## Existing source and why no database is required

`v2/backend/scanner.py` already contains an Upstox HistoryV3 API client and historical/intraday candle fetch calls. Historical data can be obtained in a separately authorized **read-only** offline/staging process and held in a sanitized local file; a new database is not required. Source code access does not grant API access, and no GitHub secret or broker credential should be copied into the repository, CI logs, issues, or ChatGPT.

## Safe data acquisition contract

1. An authorized operator uses their existing approved Upstox account/session in an isolated environment, with read-only market-data access and **no live scanner, order placement or recovery worker activation**.
2. Select approved instruments and several trading sessions including normal intraday minutes, session boundaries, and any known feed gaps. Record instrument key, exchange, timezone (Asia/Kolkata), date range, API endpoint/interval and provenance.
3. Fetch 1-minute OHLCV rows through the existing Upstox historical/intraday API integration or an approved data export. Keep tokens in the operator's environment only; never persist them in the replay dataset. Respect provider permissions and rate limits.
4. Normalize rows to `timestamp,symbol,open,high,low,close,volume` with timezone documented. Reject duplicate timestamps, impossible OHLC, negative volume, malformed rows, future/incomplete candles, and unintended off-session data; record missing minutes rather than fabricating candles.
5. Store a sanitized CSV/JSON artifact in an approved private location, **not in the Git repository**. Record a SHA-256 checksum, instrument/session inventory, missing-minute counts and the operator's explicit authorization for offline replay.
6. Run an isolated replay with persistence, broker orders, network side effects and production database access disabled. Compare decisions, warmup, session boundary behavior, market regime routing, gap handling and staleness against the agreed baseline; record discrepancies.
7. Have the scanner/replay owner sign off the provenance and results. Only then update the release checklist gate from BLOCKED to PASS/FAIL based on evidence.

## Minimum acceptance evidence

- Explicit data-use authorization and owner, with no secrets in artifacts
- Sanitized input file checksum, instrument/session/timezone metadata, data quality summary
- Exact replay command/environment and code commit SHA
- Baseline decision source, comparison report, mismatches and explanations
- Owner acceptance decision and link to privately retained evidence

## Current blocker

No authorized dataset, usable runtime access or baseline outputs have been demonstrated in this repository review. Existing synthetic test fixtures are **not** a substitute. Do not run live broker requests from CI or mark historical replay complete. The user does not need to create a database or manually write a CSV; the authorized operator can use the existing read-only Upstox integration when access is available.
