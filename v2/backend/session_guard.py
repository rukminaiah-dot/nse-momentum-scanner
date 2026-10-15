"""Pure NSE equity regular-session timestamp checks (IST, no exchange calendar)."""
from datetime import datetime, time
from zoneinfo import ZoneInfo

IST = ZoneInfo("Asia/Kolkata")
OPEN = time(9, 15)
CLOSE = time(15, 30)


def regular_session_minute(timestamp_ms):
    """Return the IST minute for regular weekday trading, otherwise None.

    This is a conservative time-of-day check, not an NSE holiday calendar.
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
