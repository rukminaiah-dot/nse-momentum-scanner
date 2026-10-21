"""Read-only historical 15-minute CSV paper backtest CLI.

CSV columns: symbol,timestamp,open,high,low,close,volume
Timestamp must include timezone offset; converted to IST candle START.
No network access, credentials, orders, or production dependencies.

Usage: python -m v2.backend.experimental_15m_csv_backtest candles.csv --cost-pct 0.15
"""
import argparse
import csv
import json
from collections import defaultdict
from datetime import datetime
from math import isfinite
from zoneinfo import ZoneInfo

from .experimental_15m_replay import replay_symbol

IST = ZoneInfo("Asia/Kolkata")


def read_bars(path):
    groups = defaultdict(list)
    with open(path, newline="", encoding="utf-8-sig") as handle:
        for row in csv.DictReader(handle):
            stamp = datetime.fromisoformat(row["timestamp"].replace("Z", "+00:00"))
            if stamp.tzinfo is None:
                raise ValueError("CSV timestamps must include timezone offset")
            stamp = stamp.astimezone(IST).replace(tzinfo=None)
            minutes = stamp.hour * 60 + stamp.minute
            if not (555 <= minutes < 930 and (minutes - 555) % 15 == 0):
                raise ValueError("CSV contains non-NSE 15-minute candle timestamp")
            bar = {"timestamp": stamp}
            for field in ("open", "high", "low", "close", "volume"):
                bar[field] = float(row[field])
                if not isfinite(bar[field]):
                    raise ValueError("Nonfinite OHLCV data")
            if not (bar["volume"] >= 0 and bar["low"] > 0 and
                    bar["low"] <= min(bar["open"], bar["close"]) <= max(bar["open"], bar["close"]) <= bar["high"]):
                raise ValueError("Invalid OHLCV candle")
            groups[row["symbol"]].append(bar)
    for symbol, bars in groups.items():
        bars.sort(key=lambda b: b["timestamp"])
        if len({b["timestamp"] for b in bars}) != len(bars):
            raise ValueError("Duplicate timestamp for " + symbol)
    return groups


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("csv_path")
    parser.add_argument("--cost-pct", type=float, required=True,
                        help="Round-trip brokerage, fees, taxes and slippage in percent")
    parser.add_argument("--stop-pct", type=float, default=0.5)
    args = parser.parse_args()
    results = [replay_symbol(symbol, bars, cost_pct=args.cost_pct,
                             stop_pct=args.stop_pct)
               for symbol, bars in sorted(read_bars(args.csv_path).items())]
    print(json.dumps({"mode": "PAPER", "symbols": len(results),
                      "cost_pct": args.cost_pct, "results": results}, sort_keys=True))


if __name__ == "__main__":
    main()
