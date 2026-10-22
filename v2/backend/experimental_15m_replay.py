"""Offline walk-forward paper replay; only completed historical candles.

Caller supplies observed 15m bars, not synthetic prices. Volume reference uses
only bars strictly before each signal session. No production scanner imports.
"""
from collections import Counter
from datetime import timedelta

from .experimental_15m_pipeline import screen_universe
from .experimental_15m_backtest import score_trade, TARGETS


def replay_symbol(symbol, bars, *, cost_pct, stop_pct=0.5, max_holding_bars=8):
    """Return conservative, non-overlapping paper outcomes and diagnostics."""
    bars = sorted(bars, key=lambda x: x["timestamp"])
    trades = []
    reasons = Counter()
    i = 52
    while i < len(bars) - 1:
        bar = bars[i]
        now = bar["timestamp"] + timedelta(minutes=15)
        prior = [b for b in bars[:i] if b["timestamp"].date() < bar["timestamp"].date()]
        result = screen_universe({symbol: bars[:i + 1]}, {symbol: prior}, now=now)
        if not result["selected"]:
            reasons.update(result["excluded"].values())
            i += 1
            continue
        candidate = result["selected"][0]
        reasons[candidate["reason"]] += 1
        if candidate["signal"] not in ("PAPER_BUY", "PAPER_SELL"):
            i += 1
            continue
        future = []
        for next_bar in bars[i + 1:i + 1 + max_holding_bars]:
            if next_bar["timestamp"].date() != bar["timestamp"].date():
                break
            if next_bar["timestamp"] != bar["timestamp"] + timedelta(minutes=15 * (len(future) + 1)):
                break
            future.append(next_bar)
        if not future:
            i += 1
            continue
        outcomes = score_trade(candidate["signal"], future, cost_pct=cost_pct,
                               stop_pct=stop_pct, max_bars=max_holding_bars)
        if outcomes:
            trades.append({"symbol": symbol, "timestamp": str(bar["timestamp"]),
                           "direction": candidate["signal"], "rvol": candidate["relative_volume"],
                           "outcomes": outcomes})
            i += max(item["holding_bars"] for item in outcomes.values()) + 1
        else:
            i += 1
    summary = {}
    for target in TARGETS:
        key = str(target)
        returns = [trade["outcomes"][key]["net_pct"] for trade in trades]
        summary[key] = {"trades": len(returns),
                        "average_net_pct": round(sum(returns) / len(returns), 4) if returns else None,
                        "net_wins": sum(value > 0 for value in returns)}
    return {"mode": "PAPER", "symbol": symbol, "trades": trades,
            "summary": summary, "reasons": dict(reasons)}
