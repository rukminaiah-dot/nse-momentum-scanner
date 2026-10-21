"""Level-based, completed-five-minute stock setup rules.

This module only evaluates supplied candles and levels. It never submits or
simulates orders. Scores are deterministic heuristic ranks, not probabilities.
"""
from dataclasses import dataclass
from datetime import datetime, timedelta, time
from math import isfinite, floor
import os

from .volume_metrics import verified_same_slot_relative_volume


@dataclass(frozen=True)
class SetupConfig:
    rvol_min: float = 1.5
    level_approach_pct: float = 0.15
    compression_bars: int = 3
    compression_range_ratio: float = 0.85
    compression_volume_ratio: float = 0.85
    candle_body_min: float = 0.50
    close_edge_fraction: float = 0.25
    min_net_reward_risk: float = 1.5
    max_bar_age_minutes: int = 7
    stop_buffer_pct: float = 0.01

    @classmethod
    def from_env(cls):
        def number(name, default, minimum=None, maximum=None):
            try:
                value = float(os.environ.get(name, default))
            except (TypeError, ValueError):
                value = float(default)
            if not isfinite(value):
                value = float(default)
            if minimum is not None:
                value = max(minimum, value)
            if maximum is not None:
                value = min(maximum, value)
            return value

        return cls(
            rvol_min=number("SCANNER_MIN_5M_RVOL", 1.5, 1.0, 10.0),
            level_approach_pct=number("SCANNER_LEVEL_APPROACH_PCT", 0.15, 0.01, 2.0),
            compression_bars=int(number("SCANNER_COMPRESSION_BARS", 3, 2, 6)),
            compression_range_ratio=number("SCANNER_COMPRESSION_RANGE_RATIO", 0.85, 0.1, 1.0),
            compression_volume_ratio=number("SCANNER_COMPRESSION_VOLUME_RATIO", 0.85, 0.1, 1.0),
            min_net_reward_risk=number("SCANNER_MIN_NET_REWARD_RISK", 1.5, 0.5, 10.0),
            max_bar_age_minutes=int(number("SCANNER_5M_MAX_AGE_MINUTES", 7, 5, 30)),
            stop_buffer_pct=number("SCANNER_STOP_BUFFER_PCT", 0.01, 0.0, 1.0),
        )


def wait_stock_setup(symbol, reason, *, last_observed_minute_candle_time=None):
    """Build a safe WAIT response when source data blocks setup evaluation."""
    return {
        "symbol": symbol, "direction": None, "status": "WAIT",
        "verified_level": None, "verified_level_name": None,
        "verified_level_source": None, "verified_level_session_date": None,
        "trigger_candle_time": None, "last_completed_candle_time": None,
        "last_completed_close": None, "last_observed_minute_candle_time": last_observed_minute_candle_time,
        "verified_levels": [], "relative_volume": None,
        "relative_volume_baseline": None, "relative_volume_status": "UNAVAILABLE",
        "ema9": None, "ema20": None, "entry_reference": None,
        "stop_invalidation": None, "trade_plan": None,
        "heuristic_rank_score": 0, "reasons": [reason],
        "order_execution_enabled": False,
    }


def _valid_bar(bar):
    try:
        values = [float(bar[name]) for name in ("open", "high", "low", "close", "volume")]
        stamp = bar.get("timestamp")
    except (AttributeError, KeyError, TypeError, ValueError, OverflowError):
        return False
    return (isinstance(stamp, datetime) and all(isfinite(v) for v in values)
            and values[1] >= max(values[0], values[3])
            and values[2] <= min(values[0], values[3])
            and values[4] >= 0 and values[1] >= values[2])


def verified_previous_day_levels(minute_rows, session_date):
    """Return PDH/PDL only from a complete, continuous 09:15–15:29 session."""
    parsed = []
    from datetime import datetime as dt
    from zoneinfo import ZoneInfo
    ist = ZoneInfo("Asia/Kolkata")
    for row in minute_rows or ():
        try:
            stamp = row[0]
            if isinstance(stamp, str):
                stamp = dt.fromisoformat(stamp.replace("Z", "+00:00"))
            if stamp.tzinfo is not None:
                stamp = stamp.astimezone(ist).replace(tzinfo=None)
            parsed.append((stamp, float(row[2]), float(row[3])))
        except (IndexError, TypeError, ValueError, OverflowError):
            continue
    prior_days = sorted({stamp.date() for stamp, _, _ in parsed if stamp.date() < session_date})
    if not prior_days:
        return None
    day = prior_days[-1]
    rows = sorted((item for item in parsed if item[0].date() == day), key=lambda item: item[0])
    expected_start = datetime.combine(day, time(9, 15))
    expected = [expected_start + timedelta(minutes=i) for i in range(375)]
    if len(rows) != len(expected) or [item[0] for item in rows] != expected:
        return None
    highs = [row[1] for row in rows]
    lows = [row[2] for row in rows]
    if not all(isfinite(value) for value in highs + lows):
        return None
    return {"pdh": max(highs), "pdl": min(lows), "session_date": day.isoformat(),
            "source": "verified_complete_1m_upstox_session"}


def opening_range_levels(bars_5m, *, session_date, bars=3):
    """First three complete 5-minute candles (09:15–09:30) define ORH/ORL."""
    start = datetime.combine(session_date, time(9, 15))
    opening = [bar for bar in bars_5m if start <= bar["timestamp"] < start + timedelta(minutes=15)]
    expected = [start + timedelta(minutes=5 * i) for i in range(bars)]
    if len(opening) != bars or [bar["timestamp"] for bar in opening] != expected:
        return None
    if not all(_valid_bar(bar) for bar in opening):
        return None
    return {"orh": max(bar["high"] for bar in opening),
            "orl": min(bar["low"] for bar in opening),
            "session_date": session_date.isoformat(),
            "source": "verified_completed_5m_opening_range"}


def _rvol(bar, history_rows):
    return verified_same_slot_relative_volume(bar, history_rows, reference_sessions=20)


def _candle_quality(bar, direction, config):
    span = float(bar["high"]) - float(bar["low"])
    if span <= 0:
        return False, 0.0, 0.0
    body = abs(float(bar["close"]) - float(bar["open"])) / span
    close_position = (float(bar["close"]) - float(bar["low"])) / span
    if direction == "LONG":
        passed = float(bar["close"]) > float(bar["level"]) and body >= config.candle_body_min and close_position >= 1 - config.close_edge_fraction
    else:
        passed = float(bar["close"]) < float(bar["level"]) and body >= config.candle_body_min and close_position <= config.close_edge_fraction
    return passed, body, close_position


def _indicative_round_trip_cost_per_share(price):
    """Indicative India cash intraday charges per share; slippage is separate."""
    notional = float(price)
    brokerage = min(20.0, notional * 0.001) * 2
    exchange = notional * 2 * 0.0000307
    ipft = notional * 2 * 0.000000001
    stt = notional * 0.00025
    stamp = notional * 0.00003
    sebi = notional * 2 * 0.000001
    gst = 0.18 * (brokerage + exchange + ipft)
    return brokerage + exchange + ipft + stt + stamp + sebi + gst


def _trade_plan(direction, entry, stop, levels, config):
    cost = _indicative_round_trip_cost_per_share(entry)
    risk = (entry - stop) if direction == "LONG" else (stop - entry)
    if not isfinite(risk) or risk <= 0:
        return None, "Invalid stop structure"
    targets = []
    for pct in (0.01, 0.02):
        target = entry * (1 + pct if direction == "LONG" else 1 - pct)
        opposing = [float(v) for k, v in levels.items()
                    if (k in ("pdh", "orh", "resistance") if direction == "LONG"
                        else k in ("pdl", "orl", "support"))
                    and ((float(v) > entry and float(v) < target) if direction == "LONG"
                         else (float(v) < entry and float(v) > target))]
        # Only currently verified levels are considered; no synthetic VWAP/pivots.
        clear = not opposing
        net_reward = abs(target - entry) - cost
        net_risk = risk + cost
        rr = net_reward / net_risk if net_risk > 0 else None
        viable = clear and net_reward > 0 and rr is not None and rr >= config.min_net_reward_risk
        targets.append({"percent": int(pct * 100), "price": round(target, 4),
                        "viable": viable, "blocked_by": round(min(opposing) if direction == "LONG" else max(opposing), 4) if opposing else None,
                        "net_reward_per_share": round(net_reward, 4),
                        "reward_to_risk": round(rr, 3) if rr is not None else None})
    chosen = next((target for target in targets if target["viable"]), None)
    if chosen is None:
        return {"targets": targets, "estimated_charges_per_share": round(cost, 4),
                "slippage": "UNAVAILABLE", "reward_to_risk": None}, "No target has enough clear, cost-adjusted reward for the stop risk"
    return {"targets": targets, "estimated_charges_per_share": round(cost, 4),
            "slippage": "UNAVAILABLE", "reward_to_risk": chosen["reward_to_risk"],
            "selected_target_percent": chosen["percent"],
            "cost_basis": "indicative round-trip NSE cash intraday charges per 1 share; actual quantity/tariff may differ"}, None


def _compression(bars, price, levels, config):
    n = config.compression_bars
    if len(bars) < 2 * n:
        return None
    prior, recent = bars[-2 * n:-n], bars[-n:]
    prior_range = sum(bar["high"] - bar["low"] for bar in prior) / n
    recent_range = sum(bar["high"] - bar["low"] for bar in recent) / n
    prior_volume = sum(bar["volume"] for bar in prior) / n
    recent_volume = sum(bar["volume"] for bar in recent) / n
    if prior_range <= 0 or prior_volume <= 0:
        return None
    if recent_range > prior_range * config.compression_range_ratio:
        return None
    if recent_volume > prior_volume * config.compression_volume_ratio:
        return None
    nearest = min(levels.items(), key=lambda item: abs(price - item[1]) / max(price, 1e-9))
    distance_pct = abs(price - nearest[1]) / max(price, 1e-9) * 100
    if distance_pct > config.level_approach_pct:
        return None
    return {"level_name": nearest[0], "level": float(nearest[1]),
            "direction": "LONG" if nearest[0] in ("pdh", "orh") else "SHORT",
            "range_ratio": round(recent_range / prior_range, 3),
            "volume_ratio": round(recent_volume / prior_volume, 3),
            "distance_pct": round(distance_pct, 4)}


def evaluate_stock_setup(symbol, bars_5m, history_5m_rows, levels, *, now,
                         ema9=None, ema20=None, previous_state=None, config=None):
    """Return one deduplicated current setup state with explicit blockers."""
    config = config or SetupConfig()
    bars = list(bars_5m or ())
    result = {"symbol": symbol, "direction": None, "status": "WAIT",
              "verified_level": None, "verified_level_name": None,
              "verified_level_source": None, "verified_level_session_date": None,
              "trigger_candle_time": None, "last_completed_candle_time": None,
              "last_completed_close": None, "last_observed_minute_candle_time": None,
              "verified_levels": [],
              "relative_volume": None, "relative_volume_baseline": None,
              "relative_volume_status": "UNAVAILABLE", "ema9": ema9, "ema20": ema20,
              "entry_reference": None, "stop_invalidation": None, "trade_plan": None,
              "heuristic_rank_score": 0, "reasons": [], "order_execution_enabled": False}
    if not bars or not _valid_bar(bars[-1]):
        result["reasons"] = ["No verified completed 5-minute candle"]
        return result
    latest = bars[-1]
    age = now - (latest["timestamp"] + timedelta(minutes=5))
    if age < timedelta(0) or age > timedelta(minutes=config.max_bar_age_minutes):
        result["reasons"] = ["WAIT: latest completed 5-minute candle is stale or future-dated"]
        return result
    session_date = latest["timestamp"].date()
    today = [bar for bar in bars if bar.get("timestamp") and bar["timestamp"].date() == session_date]
    if any(not _valid_bar(bar) for bar in today):
        result["reasons"] = ["WAIT: malformed candle data"]
        return result
    if any(today[i]["timestamp"] - today[i-1]["timestamp"] != timedelta(minutes=5)
           for i in range(1, len(today))):
        result["reasons"] = ["WAIT: missing or non-contiguous completed 5-minute candles"]
        return result
    levels = dict(levels or {})
    opening = opening_range_levels(today, session_date=session_date)
    if opening:
        levels.update({"orh": opening["orh"], "orl": opening["orl"]})
    valid_levels = {key: float(value) for key, value in levels.items()
                    if key in ("pdh", "pdl", "orh", "orl") and value is not None
                    and isfinite(float(value)) and float(value) > 0}
    result["last_completed_candle_time"] = latest["timestamp"].isoformat()
    result["last_completed_close"] = round(float(latest["close"]), 4)
    level_sources = {
        "pdh": ("PREVIOUS_DAY_HIGH", levels.get("source"), levels.get("session_date")),
        "pdl": ("PREVIOUS_DAY_LOW", levels.get("source"), levels.get("session_date")),
        "orh": ("OPENING_RANGE_HIGH", "verified_completed_5m_opening_range", session_date.isoformat()),
        "orl": ("OPENING_RANGE_LOW", "verified_completed_5m_opening_range", session_date.isoformat()),
    }
    result["verified_levels"] = [
        {"name": level_sources[key][0], "value": round(value, 4),
         "source": level_sources[key][1] or "source_unavailable",
         "session_date": level_sources[key][2]}
        for key, value in valid_levels.items()
    ]
    if not valid_levels:
        result["reasons"] = ["WAIT: verified previous-day or opening-range levels unavailable"]
        return result
    rvol_stats = _rvol(latest, history_5m_rows)
    if rvol_stats:
        result.update(relative_volume=round(rvol_stats["relative_volume"], 3),
                      relative_volume_baseline=round(rvol_stats["baseline_volume"], 3),
                      relative_volume_status="VERIFIED_SAME_SLOT_20_SESSIONS")
    else:
        result["reasons"].append("Relative volume unavailable: fewer than 20 valid same-slot sessions")

    prev = dict(previous_state or {})
    trigger_stamp = str(prev.get("trigger_candle_time") or "")
    if prev.get("setup_id") and not trigger_stamp.startswith(session_date.isoformat()):
        # A setup cannot persist across sessions; levels and invalidation are
        # session-specific and must be re-established from fresh data.
        prev = {}
    if prev.get("status") in ("TRIGGERED", "CONFIRMED", "INVALID") and prev.get("setup_id"):
        direction = prev.get("direction")
        level = float(prev.get("verified_level"))
        result.update(direction=direction, verified_level=level,
                      verified_level_name=prev.get("verified_level_name"),
                      verified_level_source=prev.get("verified_level_source"),
                      verified_level_session_date=prev.get("verified_level_session_date"),
                      trigger_candle_time=prev.get("trigger_candle_time"),
                      setup_id=prev["setup_id"])
        crossed_back = latest["close"] < level if direction == "LONG" else latest["close"] > level
        stop = prev.get("stop_invalidation")
        stop_breached = (stop is not None and
                         (latest["close"] <= float(stop) if direction == "LONG"
                          else latest["close"] >= float(stop)))
        if crossed_back or stop_breached:
            why = ("completed candle closed back through the setup level" if crossed_back
                   else "completed candle breached the confirmed setup stop")
            result.update(status="INVALID", reasons=["INVALID: " + why])
            return result
        if prev["status"] == "TRIGGERED" and latest["timestamp"].isoformat() > str(prev.get("trigger_candle_time")):
            stop = latest["low"] if direction == "LONG" else latest["high"]
            buffer = latest["close"] * config.stop_buffer_pct / 100
            stop = stop - buffer if direction == "LONG" else stop + buffer
            plan, error = _trade_plan(direction, latest["close"], stop, valid_levels, config)
            if error:
                result.update(status="INVALID", reasons=["Confirmation held, but trade plan failed: " + error])
                return result
            result.update(status="CONFIRMED", entry_reference=round(latest["close"], 4),
                          stop_invalidation=round(stop, 4), trade_plan=plan,
                          reasons=["Completed 5-minute candle confirmed the break by holding the verified level",
                                   "EMA 9/20 shown as context only", "Read-only research signal"])
            result["heuristic_rank_score"] = _rank_score(result, latest, config)
            return result
        if prev["status"] == "CONFIRMED":
            result.update(status="CONFIRMED", entry_reference=prev.get("entry_reference"),
                          stop_invalidation=prev.get("stop_invalidation"),
                          trade_plan=prev.get("trade_plan"),
                          reasons=["Previously confirmed setup remains valid; no close through invalidation level"])
            result["heuristic_rank_score"] = int(prev.get("heuristic_rank_score", 0))
            return result
        if prev["status"] == "INVALID":
            compressed = _compression(today, latest["close"], valid_levels, config)
            if compressed is None:
                result.update(status="INVALID", reasons=["Previous setup invalidated; waiting for a new compression setup"])
                return result

    # A new completed candle must satisfy the complete breakout shape.
    candidates = []
    for name, level in valid_levels.items():
        direction = "LONG" if name in ("pdh", "orh") else "SHORT"
        candle = dict(latest, level=level)
        passed, body_ratio, close_position = _candle_quality(candle, direction, config)
        if not passed or not rvol_stats or rvol_stats["relative_volume"] < config.rvol_min:
            continue
        candidates.append((direction, name, level, body_ratio, close_position))
    if candidates:
        direction, name, level, body_ratio, close_position = max(
            candidates, key=lambda item: (rvol_stats["relative_volume"], item[3],
                                          item[4] if item[0] == "LONG" else 1-item[4],
                                          item[2] if item[0] == "LONG" else -item[2]))
        setup_id = f"{symbol}:{direction}:{name}:{level:.4f}:{latest['timestamp'].isoformat()}"
        result.update(direction=direction, status="TRIGGERED", verified_level=level,
                      verified_level_name=level_sources[name][0],
                      verified_level_source=level_sources[name][1],
                      verified_level_session_date=level_sources[name][2],
                      trigger_candle_time=latest["timestamp"].isoformat(), setup_id=setup_id,
                      reasons=["Completed 5-minute candle closed beyond verified level",
                               f"Candle body {body_ratio:.0%}; close location {close_position:.0%}",
                               f"Verified same-slot RVOL {rvol_stats['relative_volume']:.2f}× met {config.rvol_min:.2f}× threshold",
                               "Awaiting next completed candle to hold or retest successfully"])
        result["heuristic_rank_score"] = _rank_score(result, latest, config)
        return result

    compression = _compression(today, latest["close"], valid_levels, config)
    if compression:
        result.update(status="WATCH", direction=compression["direction"],
                      verified_level=compression["level"],
                      verified_level_name=level_sources[compression["level_name"]][0],
                      verified_level_source=level_sources[compression["level_name"]][1],
                      verified_level_session_date=level_sources[compression["level_name"]][2],
                      reasons=[f"Price within {compression['distance_pct']:.3f}% of verified {compression['level_name']} level",
                               f"Completed-candle range contraction {compression['range_ratio']:.2f}× and volume easing {compression['volume_ratio']:.2f}×"])
        if not rvol_stats:
            result["reasons"].append("Breakout blocked until verified 20-session same-slot RVOL is available")
        result["heuristic_rank_score"] = min(59, int(30 + 20 * (1 - compression["range_ratio"]) + 9 * (1 - compression["volume_ratio"])))
    else:
        result["reasons"].append("No completed-candle compression near a verified level")
        if rvol_stats:
            result["reasons"].append(f"Latest 5-minute RVOL {rvol_stats['relative_volume']:.2f}×; trigger threshold {config.rvol_min:.2f}×")
    return result


def _rank_score(result, candle, config):
    """Stable 0–100 setup-quality ordering heuristic; not a probability."""
    status_base = {"WATCH": 10, "TRIGGERED": 45, "CONFIRMED": 65}.get(result.get("status"), 0)
    rvol = result.get("relative_volume")
    volume_points = min(15.0, max(0.0, ((rvol or 0) - config.rvol_min) * 8 + 8))
    span = candle["high"] - candle["low"]
    body = abs(candle["close"] - candle["open"]) / span if span else 0
    edge = ((candle["close"] - candle["low"]) / span if result.get("direction") == "LONG"
            else (candle["high"] - candle["close"]) / span) if span else 0
    plan = result.get("trade_plan") or {}
    rr_points = min(15.0, max(0.0, float(plan.get("reward_to_risk") or 0) * 5))
    return max(0, min(100, int(status_base + volume_points + min(10, body * 10)
                              + min(10, max(0, edge) * 10) + rr_points)))

