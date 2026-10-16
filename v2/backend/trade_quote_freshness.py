"""Fail-closed freshness checks for simulated trade quote display."""
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

IST = ZoneInfo("Asia/Kolkata")


def quote_freshness(*, observed_at_ist=None, timestamp_verified=False, now=None,
                    max_age_seconds=90):
    """Return VERIFIED_FRESH only for trusted, timezone-aware recent quotes."""
    if timestamp_verified is not True:
        return "UNVERIFIED"
    if not isinstance(observed_at_ist, str):
        return "UNVERIFIED"
    if isinstance(max_age_seconds, bool) or not isinstance(max_age_seconds, (int, float)):
        return "UNVERIFIED"
    from math import isfinite
    if not isfinite(max_age_seconds) or max_age_seconds <= 0:
        return "UNVERIFIED"
    try:
        stamp = datetime.fromisoformat(observed_at_ist)
        if stamp.tzinfo is None or stamp.utcoffset() is None:
            return "UNVERIFIED"
        current = now or datetime.now(IST)
        if current.tzinfo is None or current.utcoffset() is None:
            return "UNVERIFIED"
        age = (current - stamp).total_seconds()
    except (TypeError, ValueError, OverflowError):
        return "UNVERIFIED"
    if age < 0:
        return "FUTURE_TIMESTAMP"
    if age > max_age_seconds:
        return "STALE"
    return "VERIFIED_FRESH"
