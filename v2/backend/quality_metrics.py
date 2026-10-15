"""Pure observed-history gap metrics; no external data or candle mutation."""
from datetime import datetime, timedelta

ONE_MINUTE = timedelta(minutes=1)


def observed_history_gaps(history, today):
    """Count missing minutes between retained same-day candle timestamps.

    A zero count is not evidence of full-session coverage. Malformed timestamps,
    mixed timezones, or invalid ordering fail closed with an unknown gap count.
    """
    minutes = []
    for candle in history:
        stamp = getattr(candle, "timestamp", None)
        if stamp is None:
            continue
        if not isinstance(stamp, datetime):
            return _result(None, len(minutes), False)
        if stamp.date() == today:
            if stamp.tzinfo is not None:
                return _result(None, len(minutes), False)
            if stamp.second or stamp.microsecond:
                return _result(None, len(minutes), False)
            minutes.append(stamp)
    ordered = all(b > a for a, b in zip(minutes, minutes[1:]))
    if not ordered:
        return _result(None, len(minutes), False)
    gaps = sum(int((b - a) / ONE_MINUTE) - 1
               for a, b in zip(minutes, minutes[1:])
               if b - a > ONE_MINUTE)
    return _result(gaps, len(minutes), True)


def _result(gaps, count, ordered):
    return {"observed_history_gap_minutes": gaps,
            "observed_history_candles_today": count,
            "observed_history_order_valid": ordered}
