"""Offline synthetic indicator drift comparison, not signal parity.

Run: python -m scripts.compare_candle_retention --history 400 --cap 60
No credentials, broker, database, or network access.
"""
import argparse
from v2.backend.indicators import ema, atr, momentum


def compare(history, cap):
    if history < 22 or cap < 21 or cap >= history:
        raise ValueError("require history > cap >= 21")
    prices = [100.0 + i * 0.05 + (2.0 if i % 7 == 0 else -0.5)
              for i in range(history)]
    maxima = {"ema9": 0.0, "ema20": 0.0, "atr14": 0.0, "momentum5": 0.0}
    for end in range(21, history + 1):
        full = prices[:end]
        limited = full[-cap:]
        def atr14(values):
            return atr([v + 1 for v in values], [v - 1 for v in values], values, 14)
        for label, calculate in (
            ("ema9", lambda x: ema(x, 9)),
            ("ema20", lambda x: ema(x, 20)),
            ("atr14", atr14),
            ("momentum5", momentum),
        ):
            drift = abs(calculate(full) - calculate(limited))
            maxima[label] = max(maxima[label], drift)
    print(f"synthetic_prefixes={history - 20} history={history} cap={cap}")
    for name, value in maxima.items():
        print(f"max_abs_{name}={value:.10f}")
    print("Scope: synthetic indicator drift only; no final BUY/SELL/HOLD parity or broker connection.")
    return maxima


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--history", type=int, default=400)
    parser.add_argument("--cap", type=int, default=60)
    args = parser.parse_args()
    compare(args.history, args.cap)
