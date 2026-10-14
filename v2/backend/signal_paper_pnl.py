"""Hypothetical equal-notional paper P&L for STOCK signals only.

No broker fills, fees, leverage, or tradable index contracts are inferred.
"""
from math import isfinite

def model_stock_pnl(report, *, notional_inr=10000, round_trip_cost_pct=0):
    """Return modeled stock outcomes, excluding indices from rupee totals.

    Fractional units are assumed for comparability; these are not executable
    share quantities. Round-trip cost is a percentage of entry notional.
    """
    for label, value in (("notional_inr", notional_inr),
                         ("round_trip_cost_pct", round_trip_cost_pct)):
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not isfinite(value):
            raise ValueError(label + " must be a finite number")
    if notional_inr <= 0 or round_trip_cost_pct < 0 or round_trip_cost_pct > 100:
        raise ValueError("notional must be positive and cost percentage between 0 and 100")
    calls = []
    for call in report["closed_calls"]:
        if call["kind"] != "stock":
            continue
        entry = float(call["buy_price"])
        exit_price = float(call["sell_price"])
        if not isfinite(entry) or not isfinite(exit_price) or entry <= 0 or exit_price <= 0:
            raise ValueError("stock entry and exit prices must be positive and finite")
        gross = notional_inr * (exit_price / entry - 1)
        cost = notional_inr * round_trip_cost_pct / 100
        net = gross - cost
        calls.append({"symbol": call["symbol"],
                      "buy_time_ist": call["buy_time_ist"],
                      "sell_time_ist": call["sell_time_ist"],
                      "gross_pnl_inr": round(gross, 2),
                      "assumed_cost_inr": round(cost, 2),
                      "net_pnl_inr": round(net, 2),
                      "outcome": "WIN" if net > 0 else "LOSS" if net < 0 else "FLAT"})
    return {
        "mode": "HYPOTHETICAL_STOCK_PAPER_MODEL",
        "notional_per_call_inr": notional_inr,
        "assumed_round_trip_cost_pct": round_trip_cost_pct,
        "stock_closed_calls": len(calls),
        "stock_wins_after_cost": sum(c["net_pnl_inr"] > 0 for c in calls),
        "stock_losses_after_cost": sum(c["net_pnl_inr"] < 0 for c in calls),
        "gross_stock_pnl_inr": round(sum(c["gross_pnl_inr"] for c in calls), 2),
        "net_stock_pnl_inr": round(sum(c["net_pnl_inr"] for c in calls), 2),
        "index_calls_excluded": sum(c["kind"] == "index" for c in report["closed_calls"]),
        "calls": calls,
        "disclaimer": "Hypothetical fractional-unit equal notional, not broker-executed returns. Slippage, taxes and real charges not verified. Index points excluded."
    }
