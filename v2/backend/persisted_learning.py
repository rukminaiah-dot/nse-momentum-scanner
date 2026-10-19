"""Safe descriptive learning summary for the persistent signal ledger.

The durable ledger does not contain entry snapshots or fee-adjusted outcomes,
so this module reports verified gross outcomes while keeping model training off.
"""

from collections import Counter
from datetime import datetime
import math


def _finite_number(value):
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return number if math.isfinite(number) else None


def _as_datetime(value):
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    return None


def learning_report_from_records(records):
    """Summarize completed persisted rows without fabricating model labels."""
    valid = 0
    invalid = 0
    loss_reasons = Counter()

    for record in records:
        buy_time = _as_datetime(record.get("buy_time"))
        sell_time = _as_datetime(record.get("sell_time"))
        buy = _finite_number(record.get("buy_price"))
        sell = _finite_number(record.get("sell_price"))
        quantity = _finite_number(record.get("quantity"))
        stored_pnl = _finite_number(record.get("pnl_total"))

        if (buy_time is None or sell_time is None or buy is None or sell is None
                or quantity is None or stored_pnl is None or buy <= 0 or sell <= 0
                or quantity <= 0):
            invalid += 1
            continue
        try:
            if buy_time.tzinfo is None or sell_time.tzinfo is None or sell_time < buy_time:
                invalid += 1
                continue
        except TypeError:
            invalid += 1
            continue

        gross_pnl = (sell - buy) * quantity
        tolerance = max(0.02, abs(gross_pnl) * 0.001)
        if abs(gross_pnl - stored_pnl) > tolerance:
            invalid += 1
            continue

        valid += 1
        if gross_pnl < 0:
            reason = str(record.get("exit_reason") or "UNSPECIFIED")
            loss_reasons[reason] += 1

    losses = sum(loss_reasons.values())
    if valid:
        model_status = "BLOCKED_CONTEXT_AND_COST_LABELS_REQUIRED"
    elif invalid:
        model_status = "INSUFFICIENT_VALID_HISTORY"
    else:
        model_status = "COLLECTING_DATA"
    return {
        "status": "PERSISTED_HISTORY_REVIEW",
        "source": "daily_trade_history",
        "closed_records_seen": len(records),
        "complete_records": valid,
        "invalid_records_excluded": invalid,
        "gross_loss_count": losses,
        "gross_loss_reasons": dict(sorted(loss_reasons.items())),
        "gross_losses_by_nifty_recovery_state": {"UNAVAILABLE": losses} if losses else {},
        "model": {
            "status": model_status,
            "recommendations_enabled": False,
        },
        "recommendations_enabled": False,
        "broker_orders_enabled": False,
        "notes": [
            "Learning and P&L use the same persistent daily_trade_history ledger.",
            "These are recorded signal outcomes, not broker-confirmed executions.",
            "Entry context and cost-adjusted net outcomes are not stored, so model training remains disabled.",
        ],
    }
