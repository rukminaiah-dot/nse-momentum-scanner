"""Offline-only boundary between calendar decisions and scanner side effects.

The live scanner does NOT call this module. All handlers must be supplied by
an isolated test harness; no Upstox, database, or network dependencies.
"""
from .offline_scanner_session_policy import classify_scanner_tick


def dispatch_offline_scanner_tick(
    key, timestamp_ms, active_minute, eligible_keys, schedule,
    start_date, end_date, source, verified, *,
    on_update, on_finalize, close_grace_minutes=5,
):
    """Run at most one caller-supplied handler after a calendar decision.

    Rejected ticks invoke neither handler. The finalize handler must itself
    be idempotent and must not create a new candle.
    """
    action = classify_scanner_tick(
        key, timestamp_ms, active_minute, eligible_keys, schedule,
        start_date, end_date, source, verified, close_grace_minutes,
    )
    if action == "UPDATE":
        on_update()
    elif action == "FINALIZE_LAST_MINUTE":
        on_finalize()
    return action
