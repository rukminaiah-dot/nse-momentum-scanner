# PR #9 — Historical replay acquisition and authorization

Status: **historical fetch and offline trace executed; acceptance remains blocked**. This handoff now records the trace evidence and the remaining parity/sign-off requirements.

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

## Completed trace evidence and current blocker

GitHub Actions [PR #9 historical replay run #5](https://github.com/rukminaiah-dot/nse-momentum-scanner/actions/runs/38958470845) completed successfully on 2026-10-16 UTC (job `offline-historical-trace`, ID `117167202498`). Its logs confirm that the exporter fetched 750 one-minute candles for `NSE_EQ|INE974X01010` (`stock`) over 2026-10-15 through 2026-10-16, ran the offline trace, and completed successfully. The raw CSV and trace were kept in temporary private runner storage and deleted at job end; they were not committed to GitHub or retained in Render. The raw file and trace were deleted by the workflow after the job. Its logs do not expose the trace checksum or signal-count summary.

This confirms the read-only export and trace path ran on real Upstox candles. It does **not** establish decision parity or acceptance: no independently produced expected-decision baseline, discrepancy report, or scanner-owner sign-off is recorded. Existing Render history contains aggregate signal readings rather than raw OHLCV candles. Synthetic fixtures are not a substitute. Keep the replay acceptance gate blocked until the baseline and owner decision are recorded; do not describe the successful trace as a parity pass.

## Read-only exporter

`scripts/export_upstox_historical_readonly.py` uses Upstox's read-only HistoryV3 historical-candle endpoint. By default it only validates CLI inputs and prints a dry-run notice; `--execute` is required to make a request. It imports no scanner, order, or database code, rejects malformed/off-session/duplicate rows and refuses to overwrite files. Use a private path outside the repository and an approved completed-date range. The tool was run by workflow #5 against Upstox. That successful trace is not replay acceptance: an independently produced expected-decision baseline, discrepancy report, and scanner-owner sign-off are still missing.

Example dry run (no network):

```sh
python scripts/export_upstox_historical_readonly.py --instrument-key 'NSE_EQ|APPROVED_KEY' --from-date 2026-10-12 --to-date 2026-10-13 --output /tmp/approved-private-candles.csv
```

An authorized operator must substitute a real approved instrument key and separately authorize any `--execute` invocation. Never put tokens in command arguments or logs.

## Offline trace runner

To reproduce the existing trace with a newly authorized private CSV export, run from the repository root in an isolated environment:

```sh
python scripts/replay_historical_candles_offline.py --input /private/approved-candles.csv --output /private/replay-trace.json --kind stock
```

Use `--kind primary-index` or `secondary-index` for approved index datasets. This validates and fingerprints the CSV, reports missing minutes, and produces per-minute offline-model decisions. **It does not establish full scanner parity or acceptance**: a scanner owner must compare the trace against independently approved expected decisions and validate lifecycle/persistence/order boundaries. Do not upload raw data or trace to public CI/artifacts without data-custodian permission.
