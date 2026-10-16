"""Offline scanner-level synthetic retention comparison (no scanner import).

Run: python -m scripts.compare_offline_scanner_retention --cap 60
"""
import argparse
from datetime import datetime, timedelta
from v2.backend.candles import Candle
from v2.backend.offline_signal_parity import evaluate


def compare(cap, history=400):
    if cap < 21 or history <= cap:
        raise ValueError("require history > cap >= 21")
    start = datetime(2026, 10, 16, 9, 15)
    regimes = {
        "trend": [100 + i * 0.03 for i in range(history)],
        "reversal": [100 + i * 0.05 if i < history // 2
                     else 100 + (history - i) * 0.05 for i in range(history)],
        "high_seed_tiny_uptrend": ([150.0] * (history - 60)
                                   + [100.0 + i * 0.0001 for i in range(60)]),
        "low_seed_tiny_downtrend": ([50.0] * (history - 60)
                                    + [100.0 - i * 0.0001 for i in range(60)]),
    }
    count = 0
    mismatches = []
    for name, closes in regimes.items():
        candles = []
        for i, close in enumerate(closes):
            candle = Candle(close, 100.0)
            candle.timestamp = start + timedelta(minutes=i)
            candles.append(candle)
        for end in range(21, history + 1):
            full = candles[:end]
            short = full[-cap:]
            for kind, is_index, is_stock, is_primary in (
                ("primary_index", True, False, True),
                ("secondary_index", True, False, False),
                ("stock", False, True, False)):
                # All timestamps are intentionally on the same synthetic
                # calendar date, so a 400-minute replay spans a simulated
                # session; no market-hours claim is made.
                full_decision = evaluate(full, session_date=start.date(),
                                         is_index=is_index, is_stock=is_stock,
                                         is_primary_index=is_primary)
                short_decision = evaluate(short, session_date=start.date(),
                                          is_index=is_index, is_stock=is_stock,
                                          is_primary_index=is_primary)
                count += 1
                if full_decision["signal"] != short_decision["signal"]:
                    mismatches.append((name, kind, end,
                                       full_decision["signal"],
                                       short_decision["signal"]))
    print(f"offline_scanner_comparisons={count} history={history} cap={cap}")
    print(f"offline_scanner_disagreements={len(mismatches)}")
    for kind in ("primary_index", "secondary_index", "stock"):
        print(f"instrument_disagreements kind={kind} count="
              f"{sum(item[1] == kind for item in mismatches)}")
    for name, kind, end, full, short in mismatches[:12]:
        print(f"scanner_disagreement regime={name} kind={kind} "
              f"prefix={end} unlimited={full} capped={short}")
    print("Scope: isolated synthetic calculation model, not live scanner or orders.")
    return mismatches


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--cap", type=int, default=60)
    parser.add_argument("--history", type=int, default=400)
    args = parser.parse_args()
    compare(args.cap, args.history)
