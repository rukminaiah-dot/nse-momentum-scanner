"""Research definition for a sustained, medium-term NIFTY reversal.

This is a target-labeling and rule-specification module, not a trained model.
It intentionally emits no forecast probability until point-in-time history has
been assembled and validated out of sample.
"""
from __future__ import annotations

import math
from typing import Any


HORIZON_SESSIONS = 60
TARGET_POINTS = 500.0
PERSISTENCE_SESSIONS = 15
MIN_PERSISTENT_CLOSES = 10
PRIOR_SESSIONS = 60


def rule_definition() -> dict[str, Any]:
    """Return an explicit, provisional multi-week reversal target."""
    return {
        "status": "RESEARCH_RULES_ONLY",
        "probability_status": "NOT_BACKTESTED",
        "probabilities": None,
        "horizon_trading_sessions": HORIZON_SESSIONS,
        "approximate_horizon": "about three months; medium-term, not multi-year",
        "target_points": TARGET_POINTS,
        "target_pct": None,
        "reversal_target": (
            "A confirmed medium-term reversal requires a 500-point move from the verified "
            "anchor close against the preceding trend, with at least 10 of the final 15 "
            "completed-session closes in the 60-session horizon remaining beyond that "
            "500-point barrier. Before that persistence condition is observed, it is only a "
            "reversal watch. The 10-of-15 rule is a proposed label definition, not a validated "
            "market edge."
        ),
        "prior_trend_rule": (
            "Use only the 60 completed daily closes available by cutoff. Classify UP when both "
            "the latest-20-session return and SMA20>SMA50; classify DOWN when both indicate "
            "down; otherwise classify MIXED and withhold a reversal direction."
        ),
        "watch_evidence": (
            "A watch may be raised when completed price structure turns against the prior "
            "trend and at least two independent fresh confirmations support it: named-proxy "
            "relative volume/breadth, India VIX behavior, same-date published FII/FPI-DII cash "
            "flows, or timestamped macro/news context. P/E remains context only."
        ),
        "data_status": "REQUIRES_POINT_IN_TIME_HISTORICAL_DATA",
        "probability_guard": (
            "Do not show calibrated probabilities until the target is tested with chronological "
            "walk-forward validation and an untouched final holdout."
        ),
    }


def classify_sustained_reversal(
    anchor_close: Any,
    prior_closes: list[Any],
    future_closes: list[Any],
) -> dict[str, Any]:
    """Label a 60-session path using only closes; intended for retrospective evaluation."""
    try:
        anchor = float(anchor_close)
        if not math.isfinite(anchor) or anchor <= 0:
            raise ValueError
    except (TypeError, ValueError, OverflowError):
        return {"status": "INVALID_ANCHOR", "outcome": None}

    if not isinstance(prior_closes, list) or len(prior_closes) < PRIOR_SESSIONS:
        return {"status": "INSUFFICIENT_PRIOR_HISTORY", "outcome": None,
                "required_sessions": PRIOR_SESSIONS,
                "observed_sessions": len(prior_closes) if isinstance(prior_closes, list) else 0}
    if not isinstance(future_closes, list) or len(future_closes) < HORIZON_SESSIONS:
        return {"status": "INCOMPLETE_FUTURE_HORIZON", "outcome": None,
                "required_sessions": HORIZON_SESSIONS,
                "observed_sessions": len(future_closes) if isinstance(future_closes, list) else 0}

    try:
        prior = [float(value) for value in prior_closes[-PRIOR_SESSIONS:]]
        future = [float(value) for value in future_closes[:HORIZON_SESSIONS]]
        if any(not math.isfinite(value) or value <= 0 for value in prior + future):
            raise ValueError
    except (TypeError, ValueError, OverflowError):
        return {"status": "INVALID_CLOSE_HISTORY", "outcome": None}

    sma20 = sum(prior[-20:]) / 20
    sma50 = sum(prior[-50:]) / 50
    return20 = prior[-1] / prior[-21] - 1
    if return20 > 0 and sma20 > sma50:
        regime = "UP"
    elif return20 < 0 and sma20 < sma50:
        regime = "DOWN"
    else:
        regime = "MIXED"

    up_level, down_level = anchor + TARGET_POINTS, anchor - TARGET_POINTS
    tail = future[-PERSISTENCE_SESSIONS:]
    up_persistent = sum(value >= up_level for value in tail)
    down_persistent = sum(value <= down_level for value in tail)
    up_touched = any(value >= up_level for value in future)
    down_touched = any(value <= down_level for value in future)

    if up_persistent >= MIN_PERSISTENT_CLOSES:
        direction = "UP"
        event_type = "REVERSAL" if regime == "DOWN" else "CONTINUATION" if regime == "UP" else "UNCLASSIFIED_TREND"
        outcome = f"SUSTAINED_{direction}_{event_type}"
    elif down_persistent >= MIN_PERSISTENT_CLOSES:
        direction = "DOWN"
        event_type = "REVERSAL" if regime == "UP" else "CONTINUATION" if regime == "DOWN" else "UNCLASSIFIED_TREND"
        outcome = f"SUSTAINED_{direction}_{event_type}"
    elif up_touched or down_touched:
        direction, outcome = None, "THRESHOLD_TOUCHED_NOT_SUSTAINED"
    else:
        direction, outcome = None, "NO_500_POINT_MOVE"

    return {
        "status": "LABELED",
        "outcome": outcome,
        "prior_regime": regime,
        "direction": direction,
        "anchor_close": anchor,
        "up_level": round(up_level, 2),
        "down_level": round(down_level, 2),
        "up_touches_in_final_15": up_persistent,
        "down_touches_in_final_15": down_persistent,
        "persistence_required": MIN_PERSISTENT_CLOSES,
        "sessions_evaluated": HORIZON_SESSIONS,
    }
