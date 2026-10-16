# Verified gap recovery: manual acceptance gate

This checklist records **evidence requirements**, not a claim that the
live system has passed. Run only in an authorized, isolated environment.
Do not deploy, merge, enable trading, change database networking, or run
mutating archive commands as part of verification.

## 1. Confirm the candidate

- Record feature-branch commit SHA, GitHub Actions run URLs and conclusions.
- Confirm the candidate is the intended commit of draft PR #5.
- Keep credentials, broker instrument identifiers, connection strings,
  raw market responses, and sensitive database contents out of public logs.

## 2. Reconcile the currently available SQLite rows

In an authorized environment with access to the correct **existing** SQLite
file and PostgreSQL database, configure `DATABASE_URL` securely and run:

```sh
python -m v2.backend.signal_archive_cli verify
```

The verify command uses SQLite read-only mode and requests a PostgreSQL
read-only transaction. It does **not** initialize or synchronize the archive.

Capture the command exit code and its redacted JSON report. Acceptance
requires exit code 0, `status: MATCHED_AVAILABLE_SOURCE`,
`available_source_reconciliation_verified: true`, a nonzero
`sqlite_available_observations`, and zero missing, mismatched, and duplicate
source/archive candle keys. Investigate all nonzero exit codes; do not
reclassify archive-only rows as corruption without evidence.

**Important:** `historical_completeness_verified` remains `false` even
after a successful comparison. Rows already lost from SQLite cannot be
recovered or certified by comparing the surviving rows.

If PostgreSQL is unreachable due to an IP allowlist or the SQLite file is
unavailable, record **BLOCKED**, not PASS. Do not broaden production network
access just to complete this checklist.

## 3. Collect genuine forward paper BUY/SELL evidence

- Record the actual collection interval, source, candidate commit, and
  timestamp convention (naive IST for the paper ledger).
- Preserve a redacted, traceable sample of genuine forward-generated BUY
  and SELL signals, including symbol, candle time, signal, and positive price.
- Verify pairing, duplicate handling, rejected events, and stock/index
  separation in the paper ledger and cumulative report.
- Record unmatched BUYs and SELLs explicitly. Do not fabricate trades or
  claim broker execution, fills, fees, or realized returns.
- If no real qualifying signals occur, mark this gate **INCONCLUSIVE**.

## 4. Broker-backed gap recovery

Run only the repository's documented isolated read-only probe in an
authorized non-production environment with a temporary broker token.
Preserve redacted outcomes and evidence of independent authenticated
historical fetches, verified candle values, idempotent merge, and cleanup.
A controlled omitted-candle exercise does not establish that a natural
websocket gap has been observed. Record those as separate claims.

Do not submit orders or modify production candle state to create a test.

## 5. Review decision

| Gate | Current evidence |
| --- | --- |
| Feature-branch CI | Record latest three workflow run URLs and results |
| Available-source reconciliation | Pending authenticated read-only run |
| Historical completeness | Not verifiable from currently available SQLite |
| Forward-collected paper BUY/SELL | Pending genuine observations |
| Broker-backed isolated recovery | Pending authenticated evidence |
| Natural websocket gap | Not established by a controlled exercise |
| PR review and merge approval | Pending |

Only mark a gate PASS with reproducible evidence. Leave PR #5 as draft
until the operator reviews the evidence and explicitly approves next steps.
