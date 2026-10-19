"""Shadow-only trade learning utilities.

This module records verified decision context and summarizes completed signal
outcomes. Its recovery labels and model diagnostics never place orders or
change the scanner's BUY/SELL rules.
"""
from __future__ import annotations

import json
import math
import sqlite3
from collections import Counter
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from .database import DB_PATH


IST = ZoneInfo("Asia/Kolkata")
DEFAULT_LARGE_MOVE_PCT = 0.01
DEFAULT_ATR_MULTIPLIER = 2.0
MAX_CONTEXT_BYTES = 16_384


def _number(value):
    if isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return number if math.isfinite(number) else None


def classify_market_recovery(
    previous_close,
    session_low,
    current_price,
    atr_value=None,
    *,
    prior_recovery_fraction=0.0,
    trend=None,
    above_vwap=None,
    large_move_pct=DEFAULT_LARGE_MOVE_PCT,
    atr_multiplier=DEFAULT_ATR_MULTIPLIER,
):
    """Classify a reversal only after a volatility-scaled large decline.

    The large-move threshold is the greater of 1% of previous close and two
    ATRs by default. Thus 300 points is an example value, not a fixed rule.
    Confirmation needs independent bullish trend and VWAP evidence.
    """
    previous_close = _number(previous_close)
    session_low = _number(session_low)
    current_price = _number(current_price)
    atr_value = _number(atr_value)
    large_move_pct = _number(large_move_pct)
    atr_multiplier = _number(atr_multiplier)
    prior_recovery_fraction = _number(prior_recovery_fraction) or 0.0

    if (previous_close is None or session_low is None or current_price is None
            or previous_close <= 0 or session_low <= 0 or current_price <= 0
            or session_low > current_price or large_move_pct is None
            or large_move_pct <= 0 or atr_multiplier is None or atr_multiplier < 0):
        return {"status": "UNAVAILABLE", "reversal_eligible": False}

    decline_points = max(0.0, previous_close - session_low)
    atr_floor = max(0.0, atr_value or 0.0) * atr_multiplier
    threshold_points = max(previous_close * large_move_pct, atr_floor)
    decline_pct = decline_points / previous_close
    recovery_points = max(0.0, current_price - session_low)
    recovery_fraction = recovery_points / decline_points if decline_points else 0.0
    large_move = decline_points >= threshold_points

    status = "NO_LARGE_MOVE"
    if large_move:
        status = "BEARISH"
        if (prior_recovery_fraction >= 0.25
                and recovery_fraction < prior_recovery_fraction - 0.10):
            status = "REVERSAL_FAILED"
        elif (recovery_fraction >= 0.50 and current_price >= previous_close
              and trend == "BULLISH" and above_vwap is True):
            status = "CONFIRMED_LONG"
        elif recovery_fraction >= 0.25:
            status = "POSSIBLE_REVERSAL"
        elif recovery_fraction >= 0.10:
            status = "WEAKENING_SELLING"

    return {
        "status": status,
        "reversal_eligible": bool(large_move),
        "previous_close": previous_close,
        "session_low": session_low,
        "current_price": current_price,
        "large_move_threshold_points": round(threshold_points, 4),
        "decline_points": round(decline_points, 4),
        "decline_pct": round(decline_pct, 8),
        "recovery_points": round(recovery_points, 4),
        "recovery_fraction": round(recovery_fraction, 8),
        "trend": trend if isinstance(trend, str) else None,
        "above_vwap": above_vwap if isinstance(above_vwap, bool) else None,
    }


def serialize_context(context):
    if context is None:
        return None
    if not isinstance(context, dict):
        raise ValueError("decision context must be an object")
    payload = json.dumps(context, sort_keys=True, separators=(",", ":"), allow_nan=False)
    if len(payload.encode("utf-8")) > MAX_CONTEXT_BYTES:
        raise ValueError("decision context exceeds the storage limit")
    return payload


FEATURE_NAMES = (
    "price_vs_ema9_pct", "price_vs_ema20_pct", "momentum_pct", "rvol",
    "atr_pct", "nifty_decline_pct", "nifty_recovery_fraction",
    "nifty_bearish", "nifty_weakening", "nifty_possible_reversal",
    "nifty_confirmed_long", "nifty_reversal_failed", "banknifty_recovery_fraction",
    "banknifty_possible_reversal", "banknifty_confirmed_long",
)


def _features(context_json):
    try:
        context = json.loads(context_json or "{}")
    except (TypeError, json.JSONDecodeError):
        context = {}
    context = context if isinstance(context, dict) else {}
    raw = context.get("features", {})
    raw = raw if isinstance(raw, dict) else {}
    recovery = context.get("market_recovery", {})
    recovery = recovery if isinstance(recovery, dict) else {}
    nifty = recovery.get("NIFTY 50", {})
    nifty = nifty if isinstance(nifty, dict) else {}
    bank = recovery.get("BANK NIFTY", {})
    bank = bank if isinstance(bank, dict) else {}
    values = {
        "price_vs_ema9_pct": _number(raw.get("price_vs_ema9_pct")),
        "price_vs_ema20_pct": _number(raw.get("price_vs_ema20_pct")),
        "momentum_pct": _number(raw.get("momentum_pct")),
        "rvol": _number(raw.get("rvol")),
        "atr_pct": _number(raw.get("atr_pct")),
        "nifty_decline_pct": _number(nifty.get("decline_pct")),
        "nifty_recovery_fraction": _number(nifty.get("recovery_fraction")),
        "banknifty_recovery_fraction": _number(bank.get("recovery_fraction")),
    }
    status = nifty.get("status")
    bank_status = bank.get("status")
    for key, expected in (
        ("nifty_bearish", "BEARISH"), ("nifty_weakening", "WEAKENING_SELLING"),
        ("nifty_possible_reversal", "POSSIBLE_REVERSAL"),
        ("nifty_confirmed_long", "CONFIRMED_LONG"),
        ("nifty_reversal_failed", "REVERSAL_FAILED"),
        ("banknifty_possible_reversal", "POSSIBLE_REVERSAL"),
        ("banknifty_confirmed_long", "CONFIRMED_LONG"),
    ):
        source = bank_status if key.startswith("banknifty_") else status
        values[key] = 1.0 if source == expected else 0.0
    # Missing measurements stay distinguishable from true zeroes.
    vector = []
    for name in FEATURE_NAMES:
        value = values.get(name)
        vector.append(value if value is not None else 0.0)
        if name in {"price_vs_ema9_pct", "price_vs_ema20_pct", "momentum_pct",
                    "rvol", "atr_pct", "nifty_decline_pct",
                    "nifty_recovery_fraction", "banknifty_recovery_fraction"}:
            vector.append(0.0 if value is not None else 1.0)
    return vector


def _train_logistic(rows):
    """Fit and time-split evaluate a tiny pure-Python shadow logistic model."""
    rows = sorted(rows, key=lambda row: row["signal_time"])
    rows = [row for row in rows if row.get("entry_context")]
    if len(rows) < 100:
        return {"status": "COLLECTING_DATA", "required_contextual_trades": 100}
    split = int(len(rows) * 0.8)
    train, test = rows[:split], rows[split:]
    labels_train = [int(row["net_pnl"] < 0) for row in train]
    labels_test = [int(row["net_pnl"] < 0) for row in test]
    train_counts = Counter(labels_train)
    if set(train_counts) != {0, 1} or min(train_counts.values()) < 20:
        return {"status": "INSUFFICIENT_CLASS_BALANCE", "required_per_class": 20}
    test_counts = Counter(labels_test)
    if set(test_counts) != {0, 1} or min(test_counts.values()) < 5:
        return {"status": "INSUFFICIENT_VALIDATION_BALANCE", "required_per_class": 5}

    x_train = [_features(row["entry_context"]) for row in train]
    x_test = [_features(row["entry_context"]) for row in test]
    width = len(x_train[0])
    means = [sum(row[i] for row in x_train) / len(x_train) for i in range(width)]
    scales = []
    for i in range(width):
        variance = sum((row[i] - means[i]) ** 2 for row in x_train) / len(x_train)
        scales.append(math.sqrt(variance) if variance > 1e-12 else 1.0)
    x_train = [[(v - means[i]) / scales[i] for i, v in enumerate(row)] for row in x_train]
    x_test = [[(v - means[i]) / scales[i] for i, v in enumerate(row)] for row in x_test]

    weights = [0.0] * width
    bias = 0.0
    rate = 0.08
    for _ in range(700):
        grad = [0.0] * width
        bias_grad = 0.0
        for row, label in zip(x_train, labels_train):
            z = max(-30.0, min(30.0, bias + sum(w * v for w, v in zip(weights, row))))
            probability = 1.0 / (1.0 + math.exp(-z))
            error = probability - label
            bias_grad += error
            for i, value in enumerate(row):
                grad[i] += error * value
        count = len(x_train)
        bias -= rate * bias_grad / count
        weights = [w - rate * (g / count + 0.01 * w) for w, g in zip(weights, grad)]

    def predict(row):
        z = max(-30.0, min(30.0, bias + sum(w * v for w, v in zip(weights, row))))
        return 1.0 / (1.0 + math.exp(-z))

    predictions = [predict(row) for row in x_test]
    brier = sum((p - y) ** 2 for p, y in zip(predictions, labels_test)) / len(test)
    base_rate = sum(labels_train) / len(labels_train)
    baseline = sum((base_rate - y) ** 2 for y in labels_test) / len(test)
    return {
        "status": "SHADOW_VALIDATED" if brier < baseline else "NOT_BETTER_THAN_BASELINE",
        "train_trades": len(train),
        "validation_trades": len(test),
        "validation_brier": round(brier, 6),
        "baseline_brier": round(baseline, 6),
        "recommendations_enabled": False,
    }


def learning_report(db_path=DB_PATH):
    """Summarize only complete stored records; never invent missing outcomes."""
    path = Path(db_path)
    if not path.exists():
        return _empty_report("NO_STORAGE")
    con = sqlite3.connect(path, timeout=5)
    con.row_factory = sqlite3.Row
    try:
        tables = {row[0] for row in con.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")}
        if "trades" not in tables:
            return _empty_report("NO_TRADE_TABLE")
        columns = {row[1] for row in con.execute("PRAGMA table_info(trades)")}
        has_net_pnl = "net_realized_pnl" in columns
        has_snapshots = "trade_decision_snapshots" in tables
        if has_snapshots:
            entry_expr = "(SELECT context_json FROM trade_decision_snapshots s WHERE s.trade_id=t.id AND s.stage='BUY' ORDER BY s.id LIMIT 1)"
            exit_expr = "(SELECT context_json FROM trade_decision_snapshots s WHERE s.trade_id=t.id AND s.stage='SELL' ORDER BY s.id DESC LIMIT 1)"
        else:
            entry_expr = "NULL"
            exit_expr = "NULL"
        net_expr = "t.net_realized_pnl" if has_net_pnl else "NULL"
        rows = con.execute(f"""
            SELECT t.id,t.symbol,t.signal_time,t.entry_price,t.exit_time,t.exit_price,
                   t.realized_pnl,t.exit_reason,{net_expr} AS net_realized_pnl,
                   {entry_expr} AS entry_context,{exit_expr} AS exit_context
            FROM trades t
            WHERE t.status IN ('CLOSED','SELL') AND t.exit_time IS NOT NULL
            ORDER BY t.signal_time,t.id
        """).fetchall()
    except sqlite3.Error:
        return _empty_report("STORAGE_UNAVAILABLE")
    finally:
        con.close()

    complete = []
    invalid = 0
    reasons = Counter()
    recovery = Counter()
    for row in rows:
        entry, exit_price = _number(row["entry_price"]), _number(row["exit_price"])
        gross = _number(row["realized_pnl"])
        if entry is None or entry <= 0 or exit_price is None or exit_price <= 0 or gross is None:
            invalid += 1
            continue
        try:
            bought = datetime.fromisoformat(row["signal_time"])
            sold = datetime.fromisoformat(row["exit_time"])
            if bought.tzinfo is None:
                bought = bought.replace(tzinfo=IST)
            if sold.tzinfo is None:
                sold = sold.replace(tzinfo=IST)
            if sold < bought:
                invalid += 1
                continue
        except (TypeError, ValueError):
            invalid += 1
            continue
        actual_gross = exit_price - entry
        if abs(actual_gross - gross) > max(0.02, abs(actual_gross) * 0.001):
            invalid += 1
            continue
        record = dict(row)
        record["signal_time"] = bought.isoformat()
        record["net_pnl"] = _number(row["net_realized_pnl"])
        record["gross_pnl"] = actual_gross
        complete.append(record)
        if actual_gross < 0:
            reasons[row["exit_reason"] or "UNSPECIFIED"] += 1
        try:
            context = json.loads(row["exit_context"] or "{}")
            market = context.get("market_recovery", {})
            nifty = market.get("NIFTY 50", {}) if isinstance(market, dict) else {}
            state = nifty.get("status") if isinstance(nifty, dict) else None
        except (TypeError, json.JSONDecodeError):
            state = None
        if actual_gross < 0:
            recovery[state or "UNAVAILABLE"] += 1

    model = {"status": "COLLECTING_DATA", "required_closed_trades": 100}
    net_rows = [row for row in complete if row["net_pnl"] is not None]
    if complete and not has_net_pnl:
        model = {"status": "BLOCKED_COST_ADJUSTED_LABELS_REQUIRED"}
    elif has_net_pnl:
        model = _train_logistic(net_rows)
    return {
        "status": "READY_FOR_SHADOW_REVIEW" if complete else "COLLECTING_DATA",
        "closed_records_seen": len(rows),
        "complete_records": len(complete),
        "invalid_records_excluded": invalid,
        "gross_loss_count": sum(reasons.values()),
        "gross_loss_reasons": dict(sorted(reasons.items())),
        "gross_losses_by_nifty_recovery_state": dict(sorted(recovery.items())),
        "model": model,
        "recommendations_enabled": False,
        "broker_orders_enabled": False,
        "notes": [
            "Loss summaries use complete stored signal records only.",
            "Model training requires cost-adjusted net outcomes and a time-ordered validation sample.",
            "Market recovery is context for review, never a standalone reason to delay a protective exit.",
        ],
    }


def _empty_report(status):
    return {
        "status": status,
        "closed_records_seen": 0,
        "complete_records": 0,
        "invalid_records_excluded": 0,
        "gross_loss_count": 0,
        "gross_loss_reasons": {},
        "gross_losses_by_nifty_recovery_state": {},
        "model": {"status": "COLLECTING_DATA"},
        "recommendations_enabled": False,
        "broker_orders_enabled": False,
        "notes": ["No complete history was available; no outcome was inferred."],
    }
