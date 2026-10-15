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
