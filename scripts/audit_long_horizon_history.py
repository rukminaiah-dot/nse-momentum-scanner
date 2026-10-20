#!/usr/bin/env python3
"""Audit a point-in-time NIFTY panel and label sustained 500-point outcomes.

This tool deliberately does not fit a forecast model. It reports data coverage,
labels, and chronological base rates so that missing or late-published inputs
cannot silently become features. The CSV format is documented in
docs/long-horizon-data-audit.md.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import sys
from collections import Counter
from datetime import date, datetime
from pathlib import Path
from typing import Any

from v2.backend.long_horizon_reversal import classify_sustained_reversal


FACTORS = {
    "volume_proxy": ("volume_available_at", "volume_source"),
    "india_vix": ("vix_available_at", "vix_source"),
    "fii_net": ("flows_available_at", "flows_source"),
    "dii_net": ("flows_available_at", "flows_source"),
    "nifty_pe": ("pe_available_at", "pe_source"),
    "news_count": ("news_available_at", "news_source"),
}
REQUIRED_HEADERS = {
    "session_date", "cutoff_at", "close", "close_available_at", "source"
}


def _timestamp(value: str) -> datetime | None:
    raw = (value or "").strip()
    if not raw:
        return None
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo is not None else None


def _number(value: str) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def _load(path: Path) -> tuple[list[dict[str, str]], list[str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        headers = reader.fieldnames or []
        missing = sorted(REQUIRED_HEADERS - set(headers))
        if missing:
            raise ValueError("missing required CSV columns: " + ", ".join(missing))
        rows = list(reader)
    indexed: dict[date, dict[str, str]] = {}
    for row_number, row in enumerate(rows, start=2):
        try:
            day = date.fromisoformat((row.get("session_date") or "").strip())
        except ValueError as exc:
            raise ValueError(f"row {row_number}: invalid session_date") from exc
        if day in indexed:
            raise ValueError(f"row {row_number}: duplicate session_date {day}")
        row["_day"] = day.isoformat()
        indexed[day] = row
    return [indexed[day] for day in sorted(indexed)], headers


def audit(path: Path) -> dict[str, Any]:
    rows, headers = _load(path)
    if len(rows) < 2:
        raise ValueError("at least two dated rows are required")

    # A data row is feature-eligible only when its close and cutoff are both
    # timestamped, timezone-aware, and the source says the close was available.
    eligible_prices: list[tuple[int, float]] = []
    close_rejects = Counter()
    factor_coverage: dict[str, dict[str, int]] = {}
    for index, row in enumerate(rows):
        cutoff = _timestamp(row.get("cutoff_at", ""))
        close_time = _timestamp(row.get("close_available_at", ""))
        close = _number(row.get("close", ""))
        source = (row.get("source") or "").strip()
        if cutoff is None:
            close_rejects["missing_or_timezone_naive_cutoff"] += 1
        elif close_time is None:
            close_rejects["missing_or_timezone_naive_close_timestamp"] += 1
        elif close_time > cutoff:
            close_rejects["close_published_after_cutoff"] += 1
        elif close is None or close <= 0:
            close_rejects["invalid_close"] += 1
        elif not source:
            close_rejects["missing_close_source"] += 1
        else:
            eligible_prices.append((index, close))

        for factor, (timestamp_column, source_column) in FACTORS.items():
            factor_coverage.setdefault(factor, {"available_by_cutoff": 0, "missing_or_late": 0})
            value = _number(row.get(factor, ""))
            stamp = _timestamp(row.get(timestamp_column, ""))
            source = (row.get(source_column) or "").strip()
            if (cutoff is not None and stamp is not None and stamp <= cutoff
                    and value is not None and source):
                factor_coverage[factor]["available_by_cutoff"] += 1
            else:
                factor_coverage[factor]["missing_or_late"] += 1

    # Labels are built only from a contiguous complete close series. If any
    # close is unusable, do not compress the series and accidentally change
    # the meaning of a trading-session horizon.
    accepted = {index: close for index, close in eligible_prices}
    prices: list[float] = []
    price_indices: list[int] = []
    for index in range(len(rows)):
        if index not in accepted:
            continue
        prices.append(accepted[index])
        price_indices.append(index)
    contiguous = len(price_indices) == len(rows) and price_indices == list(range(len(rows)))

    labels: list[dict[str, Any]] = []
    if contiguous:
        for anchor_index in range(59, len(prices) - 60):
            label = classify_sustained_reversal(
                prices[anchor_index],
                prices[anchor_index - 59:anchor_index + 1],
                prices[anchor_index + 1:anchor_index + 61],
            )
            if label.get("status") == "LABELED":
                labels.append({"row_index": anchor_index, "date": rows[anchor_index]["_day"], **label})

    # Keep 60 sessions clear of the final-test partition because adjacent
    # outcomes share future bars. This is descriptive base-rate reporting,
    # not model validation.
    split = int(len(labels) * 0.8)
    train = labels[:max(0, split - 60)]
    holdout = labels[min(len(labels), split + 60):]

    def counts(items: list[dict[str, Any]]) -> dict[str, int]:
        return dict(sorted(Counter(item["outcome"] for item in items).items()))

    first_day = date.fromisoformat(rows[0]["_day"])
    last_day = date.fromisoformat(rows[-1]["_day"])
    years = (last_day - first_day).days / 365.2425
    coverage_fraction = len(eligible_prices) / len(rows)
    return {
        "report_status": "AUDIT_ONLY_NO_FORECAST",
        "input_file": path.name,
        "source_rows": len(rows),
        "date_range": {"from": first_day.isoformat(), "through": last_day.isoformat(), "approx_years": round(years, 2)},
        "close_coverage": {
            "valid_and_available_by_cutoff": len(eligible_prices),
            "rows": len(rows),
            "fraction": round(coverage_fraction, 4),
            "rejected_rows_by_reason": dict(close_rejects),
            "single_source_field_present": "source" in headers,
            "complete_usable_series": contiguous,
        },
        "factor_coverage_by_cutoff": factor_coverage,
        "labels": {
            "definition": "60-session horizon; +/-500 points touched, and 10 of final 15 closes beyond one barrier",
            "total": len(labels),
            "chronological_training_base_rates_only": {"n": len(train), "outcomes": counts(train)},
            "embargoed_final_period_base_rates_only": {"n": len(holdout), "outcomes": counts(holdout)},
        },
        "model_status": "NOT_RUN_NO_POINT_IN_TIME_MODEL_FEATURES_OR_VALIDATION",
        "forecast_probabilities": None,
        "limitations": [
            "This script does not fit or validate a predictive model.",
            "Coverage is measured against supplied rows; it cannot prove that expected NSE sessions were not omitted.",
            "For each factor, its value and timezone-aware availability timestamp must both be present and no later than that row's cutoff.",
            "Rows with a missing, late, or invalid daily close prevent event labeling rather than being silently skipped.",
            "Base rates are descriptive and are not calibrated forecasts.",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("csv", type=Path, help="Point-in-time daily panel CSV")
    parser.add_argument("--output", type=Path, help="Write JSON report (default: stdout)")
    args = parser.parse_args()
    try:
        report = audit(args.csv)
    except (OSError, ValueError) as exc:
        print(f"audit failed: {exc}", file=sys.stderr)
        return 2
    rendered = json.dumps(report, indent=2, sort_keys=True)
    if args.output:
        args.output.write_text(rendered + "\n", encoding="utf-8")
    else:
        print(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
