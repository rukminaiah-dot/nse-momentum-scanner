"""Experimental NSE equity weekday/session-time checks (NOT an exchange calendar).

Known limitations: NSE holidays, special sessions (e.g. Muhurat trading),
unscheduled closures, and early closes are not represented. Do not enable
in production without validating an authoritative session calendar.
"""
from datetime import datetime, time, timedelta, date
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


def validate_session_coverage(schedule, start_date, end_date):
    """Check complete explicit date coverage; None means verified closed.

    This checks structure and completeness, NOT the schedule's provenance.
    All calendar dates, including weekends/holidays, must be represented.
    """
    if (not isinstance(schedule, dict)
            or not isinstance(start_date, date) or isinstance(start_date, datetime)
            or not isinstance(end_date, date) or isinstance(end_date, datetime)
            or start_date > end_date or (end_date - start_date).days > 366):
        return False
    current = start_date
    while current <= end_date:
        if current not in schedule:
            return False
        bounds = schedule[current]
        if bounds is not None:
            if (not isinstance(bounds, tuple) or len(bounds) != 2
                    or not all(isinstance(t, time) and t.tzinfo is None for t in bounds)):
                return False
            start, end = bounds
            if (start.second or start.microsecond or end.second or end.microsecond
                    or start >= end):
                return False
        current += timedelta(days=1)
    return True
