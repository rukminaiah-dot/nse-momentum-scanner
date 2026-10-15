"""Experimental NSE equity weekday/session-time checks (NOT an exchange calendar).

Known limitations: NSE holidays, special sessions (e.g. Muhurat trading),
unscheduled closures, and early closes are not represented. Do not enable
in production without validating an authoritative session calendar.
"""
from datetime import datetime, time
from zoneinfo import ZoneInfo

IST = ZoneInfo("Asia/Kolkata")
OPEN = time(9, 15)
CLOSE = time(15, 30)


def regular_session_minute(timestamp_ms):
    """Return the IST minute for regular weekday trading, otherwise None.

    This is a weekday/time-of-day check, not an NSE holiday calendar.
    No market data, candle state, or order execution is modified.
    """
    try:
        stamp = datetime.fromtimestamp(float(timestamp_ms) / 1000, IST)
    except (TypeError, ValueError, OverflowError, OSError):
        return None
    if stamp.weekday() >= 5 or not OPEN <= stamp.time() < CLOSE:
        return None
    return stamp.replace(second=0, microsecond=0, tzinfo=None)


def session_tick_action(timestamp_ms, active_minute=None):
    """Classify a tick without mutating candle state.

    A close-boundary tick may finalize an existing 15:29 candle, but must
    never start a 15:30 candle. Callers must finalize atomically and only once.
    """
    minute = regular_session_minute(timestamp_ms)
    if minute is not None:
        return "UPDATE"
    try:
        stamp = datetime.fromtimestamp(float(timestamp_ms) / 1000, IST)
    except (TypeError, ValueError, OverflowError, OSError):
        return "REJECT"
    if (active_minute is not None
            and isinstance(active_minute, datetime)
            and active_minute.tzinfo is None
            and active_minute.date() == stamp.date()
            and active_minute.time() == time(15, 29)
            and stamp.weekday() < 5
            and stamp.time() >= CLOSE):
        return "FINALIZE_LAST_MINUTE"
    return "REJECT"


def verified_session_minute(timestamp_ms, sessions):
    """Validate a tick against an explicit date -> (open, close) schedule.

    Missing dates fail closed. Sessions must come from a separately verified
    exchange calendar; this helper does not download or infer holidays.
    Weekend special sessions may be represented explicitly.
    """
    try:
        stamp = datetime.fromtimestamp(float(timestamp_ms) / 1000, IST)
    except (TypeError, ValueError, OverflowError, OSError):
        return None
    if not isinstance(sessions, dict):
        return None
    bounds = sessions.get(stamp.date())
    if (not isinstance(bounds, tuple) or len(bounds) != 2
            or not all(isinstance(t, time) and t.tzinfo is None for t in bounds)):
        return None
    start, end = bounds
    # Session boundaries must be minute-aligned, strictly ordered and same-day.
    if (start.second or start.microsecond or end.second or end.microsecond
            or start >= end or not start <= stamp.time() < end):
        return None
    return stamp.replace(second=0, microsecond=0, tzinfo=None)
