"""Offline-only, fail-closed session decision for scanner integration trials.

This module does not connect to a feed, mutate scanner state, or read env vars.
A caller must provide a separately reviewed complete dated calendar. The
acknowledgement flag and source label are not proof of authenticity.
"""
from .session_guard import accepted_calendar_tick_action


def classify_scanner_tick(
    key, timestamp_ms, active_minute, eligible_keys, schedule,
    start_date, end_date, source, verified, close_grace_minutes=5,
):
    """Classify stocks and indices uniformly; reject unknown instruments.

    UPDATE: a tick falls within the accepted calendar session.
    FINALIZE_LAST_MINUTE: a tick after the scheduled close may close the
    existing final-minute candle without starting another.
    REJECT: do not mutate any trading, candle, volume, or accepted-health state.
    """
    try:
        if (not isinstance(key, str) or not key
                or not isinstance(eligible_keys, (set, frozenset, tuple, list))
                or key not in eligible_keys):
            return "REJECT"
    except (TypeError, ValueError):
        return "REJECT"
    return accepted_calendar_tick_action(
        timestamp_ms, active_minute, schedule, start_date, end_date,
        source, verified, close_grace_minutes,
    )
