"""Transparent, uncalibrated long-reversal evidence points.

This additive checklist is not a probability model. Unknown or stale factors are
unscored, and news is context-only until its event classification is validated.
"""
from __future__ import annotations

import math
from datetime import datetime, timezone
from typing import Any


WEIGHTS = {"trend_structure": 25, "pe_trend": 15, "india_vix": 15,
           "fii_dii": 20, "volume": 15, "news": 10}


def _num(value: Any) -> float | None:
    try:
        number = float(value)
        return number if math.isfinite(number) else None
    except (TypeError, ValueError, OverflowError):
        return None


def _factor(key: str, label: str, status: str, points: int | None,
            reason: str, as_of: str | None = None, source: str | None = None) -> dict[str, Any]:
    return {"key": key, "label": label, "weight": WEIGHTS[key], "status": status,
            "points": points, "reason": reason, "as_of": as_of, "source": source}


def assess_long_reversal_evidence(price: dict[str, Any], pe: dict[str, Any],
                                  vix: dict[str, Any], flows: dict[str, Any],
                                  volume: dict[str, Any]) -> dict[str, Any]:
    """Return a 0–100 fixed-weight evidence score from available inputs only."""
    factors = []

    live_structure = (price.get("status") == "LIVE_FRESH"
                      and price.get("direction") in {"BULLISH", "BEARISH", "MIXED"})
    factors.append(_factor(
        "trend_structure", "NIFTY trend structure",
        "ASSESSED" if live_structure else "NOT_SCORED",
        WEIGHTS["trend_structure"] if live_structure and price.get("direction") == "BULLISH" else 0 if live_structure else None,
        ("Fresh 5-minute structure is bullish; this is short-term context, not a multi-day trendline test."
         if live_structure and price.get("direction") == "BULLISH" else
         "Fresh structure is not bullish, so it adds no long-reversal points." if live_structure else
         "No fresh NIFTY candles. Stored 5-minute snapshots cannot verify a multi-day trendline or support test."),
        price.get("candle_ist"), price.get("basis")))

    history = pe.get("history")
    valid_history = []
    if isinstance(history, list):
        for row in history:
            value = _num(row.get("value")) if isinstance(row, dict) else None
            session = row.get("session_date") if isinstance(row, dict) else None
            basis = row.get("basis") if isinstance(row, dict) else None
            if value is not None and value > 0 and isinstance(session, str) and session:
                valid_history.append((session, value, basis))
    valid_history.sort(key=lambda x: x[0])
    recent_pe = valid_history[-3:]
    pe_ok = len(recent_pe) == 3 and all(recent_pe[i][0] < recent_pe[i + 1][0] for i in range(2))
    if pe_ok:
        bases = {item[2] for item in recent_pe if item[2]}
        pe_ok = len(bases) <= 1
    falling_pe = pe_ok and recent_pe[0][1] > recent_pe[1][1] > recent_pe[2][1]
    factors.append(_factor(
        "pe_trend", "NIFTY P/E trend", "ASSESSED" if pe_ok else "NOT_SCORED",
        WEIGHTS["pe_trend"] if falling_pe else 0 if pe_ok else None,
        ("The three latest comparable stored daily readings are falling; valuation remains context, not a trigger."
         if falling_pe else
         "P/E is not falling across three comparable daily records." if pe_ok else
         "Need three comparable daily P/E records to assess direction; one P/E reading cannot establish a trend."),
        recent_pe[-1][0] if recent_pe else pe.get("session_date"), pe.get("source")))

    vix_value, vix_change = _num(vix.get("value")), _num(vix.get("change_pct"))
    vix_status = vix.get("status")
    vix_age = _num(vix.get("age_seconds"))
    vix_valid = (vix_status in {"AVAILABLE", "HISTORICAL"} and vix_value is not None
                 and vix_value > 0 and vix_change is not None
                 and (vix_age is None or 0 <= vix_age <= 5 * 86400))
    vix_supports = vix_valid and vix_value >= 25 and vix_change < 0
    factors.append(_factor(
        "india_vix", "India VIX", "ASSESSED" if vix_valid else "NOT_SCORED",
        WEIGHTS["india_vix"] if vix_supports else 0 if vix_valid else None,
        ("VIX is at least 25 and falling, a possible stress-exhaustion cue; not a direction forecast."
         if vix_supports else
         "Stored VIX does not meet the high-and-falling stress-exhaustion rule." if vix_valid else
         "No recent timestamped VIX value and change are available."),
        vix.get("as_of"), vix.get("source")))

    fii = (flows.get("fii") or {}).get("latest") or {}
    dii = (flows.get("dii") or {}).get("latest") or {}
    fii_value, dii_value = _num(fii.get("net_cr")), _num(dii.get("net_cr"))
    flow_date = flows.get("as_of_date")
    flows_valid = (flows.get("status") == "AVAILABLE" and flows.get("freshness") == "CURRENT"
                   and fii_value is not None and dii_value is not None
                   and fii.get("date") == flow_date and dii.get("date") == flow_date)
    absorption = _num(flows.get("latest_absorption_ratio"))
    flow_supports = (flows_valid and fii_value < 0 and dii_value > 0
                     and absorption is not None and absorption >= 1)
    factors.append(_factor(
        "fii_dii", "Same-date FII/FPI–DII cash flows", "ASSESSED" if flows_valid else "NOT_SCORED",
        WEIGHTS["fii_dii"] if flow_supports else 0 if flows_valid else None,
        ("DII buying offsets same-date FII/FPI selling by at least 1×; this is an end-of-day absorption cue."
         if flow_supports else
         "Same-date flows do not meet the DII-absorption rule." if flows_valid else
         "No current same-date FII/FPI and DII cash pair is available."),
        flow_date, "Upstox FII/DII NSE cash data"))

    volume_rows = _num(volume.get("verified_volume_rows"))
    volume_valid = volume.get("status") == "AVAILABLE" and volume_rows is not None and volume_rows > 0
    bullish_surge = _num(volume.get("bullish_surge_rows"))
    volume_supports = volume_valid and bullish_surge is not None and bullish_surge > 0
    factors.append(_factor(
        "volume", "Observed bullish volume", "ASSESSED" if volume_valid else "NOT_SCORED",
        WEIGHTS["volume"] if volume_supports else 0 if volume_valid else None,
        ("Verified bullish RVOL surges are present." if volume_supports else
         "Verified volume is present but has no qualifying bullish surge." if volume_valid else
         "No verified completed-candle volume rows are available; no volume is imputed."),
        volume.get("last_candle_ist"), volume.get("source")))

    factors.append(_factor(
        "news", "Timestamped news / macro", "CONTEXT_ONLY", None,
        "Headlines are shown with source timestamps, but are not automatically scored: event confirmation and directional impact are not validated.",
        None, "Timestamped financial-news feed"))

    assessed = [factor for factor in factors if factor["status"] == "ASSESSED"]
    points = sum(int(factor["points"] or 0) for factor in assessed) if assessed else None
    return {
        "status": "AVAILABLE" if assessed else "NOT_SCORED",
        "label": "LONG_REVERSAL_EVIDENCE_POINTS",
        "score_points": points,
        "max_points": 100,
        "assessed_factors": len(assessed),
        "total_market_factors": 5,
        "is_probability": False,
        "as_of": None,
        "factors": factors,
        "method": (
            "Fixed additive evidence points: trend structure 25, declining P/E across the three latest comparable stored readings 15, "
            "VIX >=25 and falling 15, same-date DII absorption of FII/FPI selling 20, bullish "
            "verified volume 15. Timestamped news is displayed but not scored. This heuristic is "
            "uncalibrated, not a probability or profit estimate; missing factors remain unscored."
        ),
    }
