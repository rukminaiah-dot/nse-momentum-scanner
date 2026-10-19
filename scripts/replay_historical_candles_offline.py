"""Offline historical candle decision trace; no broker, scanner or database imports.

Produces a trace for independent baseline comparison, NOT a parity pass.
"""
import argparse
import csv
import hashlib
import json
from collections import Counter
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from v2.backend.candles import Candle
from v2.backend.offline_signal_parity import evaluate

IST = ZoneInfo("Asia/Kolkata")


def load_candles(path):
    history = []
    seen = set()
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        required = {"timestamp", "open", "high", "low", "close", "volume"}
        if not required.issubset(reader.fieldnames or []):
            raise ValueError("missing candle columns")
        for row in reader:
            ts = datetime.fromisoformat(row["timestamp"])
            if ts.tzinfo is None:
                raise ValueError("timezone required")
            ts = ts.astimezone(IST)
            if ts in seen or ts.second or ts.microsecond:
                raise ValueError("duplicate or non-minute timestamp")
            seen.add(ts)
            op, hi, lo, close, volume = [float(row[k]) for k in ("open", "high", "low", "close", "volume")]
            if not (lo <= min(op, close) <= max(op, close) <= hi) or volume < 0:
                raise ValueError("invalid OHLCV")
            candle = Candle(close, volume)
            candle.open, candle.high, candle.low = op, hi, lo
            candle.timestamp = ts.replace(tzinfo=None)
            history.append(candle)
    if not history:
        raise ValueError("no candle rows")
    history.sort(key=lambda c: c.timestamp)
    return history


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--kind", choices=("stock", "primary-index", "secondary-index"), required=True)
    args = parser.parse_args()
    if args.output.exists():
        parser.error("refusing to overwrite existing report")
    candles = load_candles(args.input)
    sha = hashlib.sha256(args.input.read_bytes()).hexdigest()
    counts = Counter()
    trace = []
    gaps = []
    for i, candle in enumerate(candles):
        if i and candle.timestamp.date() == candles[i - 1].timestamp.date():
            delta = candle.timestamp - candles[i - 1].timestamp
            if delta > timedelta(minutes=1):
                gaps.append({"after": candles[i - 1].timestamp.isoformat(), "before": candle.timestamp.isoformat(), "minutes_missing": int(delta.total_seconds() // 60) - 1})
        result = evaluate(candles[:i + 1], session_date=candle.timestamp.date(),
                          is_index=args.kind != "stock", is_stock=args.kind == "stock",
                          is_primary_index=args.kind == "primary-index")
        counts[result["signal"]] += 1
        trace.append({"timestamp": candle.timestamp.isoformat(), "signal": result["signal"],
                      "reason": result.get("reason"), "trend_5m": result.get("trend_5m")})
    report = {"status": "TRACE_ONLY_NOT_ACCEPTED", "input_sha256": sha,
              "kind": args.kind, "candles": len(candles), "sessions": sorted({c.timestamp.date().isoformat() for c in candles}),
              "signal_counts": dict(counts), "gaps": gaps, "trace": trace,
              "limitations": "Offline decision model only; no independent expected baseline, live lifecycle, persistence, or order validation."}
    import os
    args.output.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(args.output, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as out:
        json.dump(report, out, indent=2)
    print(f"Offline trace saved ({len(candles)} candles); NOT an acceptance or parity pass.")


if __name__ == "__main__":
    main()
