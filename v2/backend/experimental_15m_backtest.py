"""Offline paper-only target scoring. No order placement or broker connection.

Signal at completed candle close; hypothetical entry at NEXT candle open.
Conservative intrabar ambiguity: stop wins when stop and target both touch.
"""
from math import isfinite

TARGETS = (0.3, 0.5, 0.75, 1.0)


def score_trade(direction, next_bars, *, cost_pct, stop_pct=0.5, max_bars=8):
    if direction not in ("PAPER_BUY", "PAPER_SELL") or not next_bars:
        return {}
    if not all(isfinite(v) for v in (cost_pct, stop_pct)) or cost_pct < 0 or stop_pct <= 0:
        raise ValueError("Invalid costs or stop")
    entry = float(next_bars[0]["open"])
    if not isfinite(entry) or entry <= 0:
        return {}
    sign = 1 if direction == "PAPER_BUY" else -1
    results = {}
    for target in TARGETS:
        outcome = None
        for i, bar in enumerate(next_bars[:max_bars]):
            high, low = float(bar["high"]), float(bar["low"])
            if not all(isfinite(v) for v in (high, low)) or high < low:
                return {}
            favorable = (high / entry - 1) * 100 if sign == 1 else (1 - low / entry) * 100
            adverse = (1 - low / entry) * 100 if sign == 1 else (high / entry - 1) * 100
            if adverse >= stop_pct:
                outcome = ("STOP", -stop_pct, i + 1)
                break
            if favorable >= target:
                outcome = ("TARGET", target, i + 1)
                break
        if outcome is None:
            n = min(max_bars, len(next_bars))
            final_close = float(next_bars[n - 1]["close"])
            outcome = ("TIME_EXIT", sign * (final_close / entry - 1) * 100, n)
        results[str(target)] = {"outcome": outcome[0],
                                "net_pct": round(outcome[1] - cost_pct, 4),
                                "holding_bars": outcome[2]}
    return results
