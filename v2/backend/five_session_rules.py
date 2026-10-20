"""Transparent five-session NIFTY 50 event definition and research rules.

The rules here are a research baseline, not a trained ML model. They deliberately
return no probability until a point-in-time history has passed walk-forward and
final holdout validation.
"""
from __future__ import annotations

import math
from datetime import date
from typing import Any


HORIZON_SESSIONS = 5
TARGET_POINTS = 500.0
RVOL_CONFIRMATION = 1.5
VIX_STRESS_LEVEL = 25.0
VIX_RISE_CONFIRMATION_PCT = 5.0


def event_spec(anchor_close: Any = None, anchor_date: str | None = None) -> dict[str, Any]:
    """Return target levels from a verified completed-session close, if supplied."""
    try:
        close = float(anchor_close)
        if not math.isfinite(close) or close <= 0:
            close = None
    except (TypeError, ValueError, OverflowError):
        close = None
    try:
        parsed_date = date.fromisoformat(str(anchor_date))
        valid_date = parsed_date.isoformat() == anchor_date
    except (TypeError, ValueError):
        valid_date = False
    ready = bool(close and valid_date)
    if not ready:
        close = None
    pct = round(TARGET_POINTS / close * 100, 4) if close else None
    return {
        "version": "NIFTY50_5SESSION_RULES_V1",
        "status": "READY" if ready else "AWAITING_VERIFIED_CLOSE",
        "anchor_close": close,
        "anchor_date": anchor_date if ready else None,
        "horizon_trading_sessions": HORIZON_SESSIONS,
        "target_points": TARGET_POINTS,
        "target_pct": pct,
        "up_level": round(close + TARGET_POINTS, 2) if close else None,
        "down_level": round(close - TARGET_POINTS, 2) if close else None,
        "outcome_classes": ["UP_ONLY", "DOWN_ONLY", "BOTH", "NEITHER"],
        "probability_status": "NOT_BACKTESTED",
        "probabilities": None,
    }


def classify_five_session_path(anchor_close: Any, future_bars: list[dict[str, Any]]) -> dict[str, Any]:
    """Create an outcome label from the next five completed daily OHLC bars.

    If both barriers are touched in one daily bar, their intraday order cannot
    be inferred from OHLC, so ``first_touch`` is explicitly ambiguous.
    """
    try:
        close = float(anchor_close)
        if not math.isfinite(close) or close <= 0:
            raise ValueError
    except (TypeError, ValueError, OverflowError):
        return {"status": "INVALID_ANCHOR", "outcome": None}
    if not isinstance(future_bars, list) or len(future_bars) < HORIZON_SESSIONS:
        return {"status": "INCOMPLETE_FUTURE_HORIZON", "outcome": None,
                "required_sessions": HORIZON_SESSIONS,
                "observed_sessions": len(future_bars) if isinstance(future_bars, list) else 0}

    up_level, down_level = close + TARGET_POINTS, close - TARGET_POINTS
    up_hit = down_hit = False
    first_touch = None
    for bar in future_bars[:HORIZON_SESSIONS]:
        if not isinstance(bar, dict):
            return {"status": "INVALID_FUTURE_BAR", "outcome": None}
        try:
            high, low = float(bar["high"]), float(bar["low"])
            if not math.isfinite(high) or not math.isfinite(low) or low > high:
                raise ValueError
        except (KeyError, TypeError, ValueError, OverflowError):
            return {"status": "INVALID_FUTURE_BAR", "outcome": None}
        hit_up, hit_down = high >= up_level, low <= down_level
        up_hit |= hit_up
        down_hit |= hit_down
        if first_touch is None and (hit_up or hit_down):
            first_touch = ("BOTH_SAME_SESSION" if hit_up and hit_down else
                           "UP_FIRST" if hit_up else "DOWN_FIRST")

    outcome = ("BOTH" if up_hit and down_hit else "UP_ONLY" if up_hit else
               "DOWN_ONLY" if down_hit else "NEITHER")
    return {"status": "LABELED", "outcome": outcome,
            "up_threshold_reached": up_hit, "down_threshold_reached": down_hit,
            "neither_threshold_reached": not up_hit and not down_hit,
            "first_touch": first_touch, "up_level": round(up_level, 2),
            "down_level": round(down_level, 2), "sessions_evaluated": HORIZON_SESSIONS}


def rule_definition() -> dict[str, Any]:
    """Return the auditable, provisional evidence rules for the API/UI."""
    return {
        "status": "RESEARCH_RULES_ONLY",
        "probability_status": "NOT_BACKTESTED",
        "probabilities": None,
        "direction_rule": (
            "Set the recent regime from the five-session return and close versus the 20-session "
            "trend measure; conflicting measures are MIXED. An upside reversal watch needs a "
            "prior down regime, a completed close above both the prior close and five-session "
            "average, and at least two of three confirmations: India VIX >=25 and falling, "
            "same-date DII net buying absorbing FII/FPI net selling at ratio >=1, or bullish "
            "RVOL >=1.5. A downside reversal watch mirrors this after an up regime: close below "
            "prior close and five-session average, plus at least two of VIX up >=5%, same-date "
            "FII/FPI net selling, or bearish RVOL >=1.5. If neither reversal rule qualifies, "
            "require price/volume aligned with the recent regime plus two independent fresh "
            "continuation confirmations; otherwise report NO CLEAR EDGE. These are unvalidated "
            "watch rules, not a trained event probability."
        ),
        "confirmation_rules": {
            "volume": f"Use completed-session constituent breadth/turnover or NIFTY futures volume, compared with its own history; RVOL >= {RVOL_CONFIRMATION:.1f} is a candidate confirmation, not a validated cutoff.",
            "india_vix": f"VIX >= {VIX_STRESS_LEVEL:.0f} and falling can support an exhaustion/reversal case; a rise >= {VIX_RISE_CONFIRMATION_PCT:.0f}% is a volatility-stress confirmation, not a direction by itself.",
            "fii_dii": "Use same-date NSE cash net flows only after their publication timestamp; DII positive net buying against FII/FPI net selling is an absorption cue, not an intraday signal.",
            "valuation": "Use P/E percentile only against a point-in-time history with a consistent earnings basis; context only, never a standalone trigger.",
            "news_and_crude": "Use only source-timestamped items available by cutoff. Treat crude direction as a macro channel and news as context until their historical predictive value is tested.",
        },
        "data_guards": [
            "Never use observations published after the forecast cutoff.",
            "Do not impute missing price, volume, VIX, flow, valuation, or news values.",
            "No verified completed close or insufficient daily history means PENDING, not a live call.",
            "NIFTY 50 has no directly traded cash-index volume; name the volume proxy and source.",
        ],
        "validation_plan": (
            "About ten years of point-in-time daily data; chronological walk-forward folds; "
            "reserve the final period untouched; compare base-rate/volatility baselines, logistic "
            "regression and gradient-boosted trees; report calibration, precision/recall, false "
            "alarms and volatility-regime results. Compare fixed 500-point, percentage and "
            "volatility-scaled targets."
        ),
    }
