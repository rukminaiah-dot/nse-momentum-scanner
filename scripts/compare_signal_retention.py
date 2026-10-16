"""Credential-free core signal parity probe; excludes scanner side effects.

Run: python -m scripts.compare_signal_retention --history 400 --cap 60
"""
import argparse
from v2.backend.indicators import ema, momentum
from v2.backend.signal_engine import generate_signal


def compare(history, cap):
    if history < 22 or cap < 21 or cap >= history:
        raise ValueError("require history > cap >= 21")
    regimes = {
        "trend": [100 + i * 0.03 for i in range(history)],
        "reversal": [100 + i * 0.05 if i < history // 2
                     else 100 + (history - i) * 0.05 for i in range(history)],
        "oscillation": [100 + (0.6 if i % 2 else -0.6) + i * 0.001
                        for i in range(history)],
        "flat": [100.0] * history,
    }
    total = 0
    disagreements = []
    def signal(values):
        return generate_signal(values[-1], ema(values, 9), ema(values, 20),
                               None, momentum(values), rvol=1.5, market="NEUTRAL")
    for regime, prices in regimes.items():
        for end in range(21, history + 1):
            full = signal(prices[:end])
            limited = signal(prices[max(0, end - cap):end])
            total += 1
            if full != limited:
                disagreements.append((regime, end, full, limited))
    print(f"synthetic_core_signal_comparisons={total} history={history} cap={cap}")
    print(f"core_signal_disagreements={len(disagreements)}")
    for regime, end, full, limited in disagreements[:10]:
        print(f"disagreement regime={regime} prefix={end} unlimited={full} capped={limited}")
    print("Scope: core generate_signal only; excludes 5m trend, ATR late-entry, "
          "RVOL derivation, index overrides, session continuity, persistence, and orders.")
    return disagreements


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--history", type=int, default=400)
    parser.add_argument("--cap", type=int, default=60)
    args = parser.parse_args()
    compare(args.history, args.cap)
