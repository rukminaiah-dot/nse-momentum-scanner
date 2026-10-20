# Medium-term reversal history: data audit input

`scripts/audit_long_horizon_history.py` is the first reproducible step toward
the 60-session sustained-reversal evaluation. It checks source coverage and
timestamps, then labels historical outcomes. It deliberately does **not** fit
a model, produce probabilities, or call descriptive base rates forecasts.

## CSV format

Use one row per NIFTY 50 trading session, sorted or sortable by `session_date`.
Keep missing values empty; do not forward-fill. Numeric columns must be plain
numbers. Timestamps must be ISO-8601 with a timezone offset, for example
`2026-10-20T16:05:00+05:30`. The `cutoff_at` value is the historical forecast
cutoff for that row. A value is counted as available only when its own
availability timestamp is at or before that cutoff and its source field is
present.

| Columns | Meaning |
|---|---|
| `session_date`, `cutoff_at` | NSE session date and timezone-aware forecast cutoff |
| `close`, `close_available_at`, `source` | NIFTY close, when it became available, and its official/source citation name |
| `volume_proxy`, `volume_proxy_name`, `volume_available_at`, `volume_source` | Explicitly named volume proxy; never NIFTY cash-index volume |
| `india_vix`, `vix_available_at`, `vix_source` | India VIX value and source timestamp |
| `fii_net`, `dii_net`, `flows_available_at`, `flows_source` | Same-date cash net flows and publication/availability time |
| `nifty_pe`, `pe_basis`, `pe_available_at`, `pe_source` | Valuation observation, consistent basis, and availability time |
| `news_count`, `news_available_at`, `news_source` | Count of timestamped items in a consistently defined window; this audit does not infer sentiment or impact |

Run from the repository root:

```sh
python scripts/audit_long_horizon_history.py data/nifty_point_in_time.csv \
  --output data/long_horizon_audit.json
```

The tool refuses to compress rows with unusable closes because doing so would
turn a 60-session horizon into a different calendar interval. It reports the
label frequencies in chronological early and late partitions with a 60-sample
gap. These are only descriptive base rates; the script does not implement the
requested walk-forward ML comparison, calibration, or untouched final model
test. Do not promote probabilities from this report.

## Current project limitation

The repository does not contain an archived, joined, point-in-time ten-year
panel for all factors. Current endpoint snapshots, recent FII/DII rows, and
current quotes cannot reconstruct what was available at past forecast
cutoffs. Gather official historical price/India VIX/flow exports and archive
each factor's actual publication time before adding it to a backtest. For
timestamped news, retain the original publication timestamp and source. Until
that dataset exists, model status remains unverified and no probability is
shown.
