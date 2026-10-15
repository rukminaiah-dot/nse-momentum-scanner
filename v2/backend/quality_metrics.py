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
            "observed_history_order_valid": ordered,
            "observed_history_insufficient": count < 6}


def summarize_observed_history(rows):
    """Summarize bounded observed gaps without assuming full-session coverage."""
    valid = [v for v in rows.values() if isinstance(v, dict)]
    gaps = [v["observed_history_gap_minutes"] for v in valid
            if isinstance(v.get("observed_history_gap_minutes"), int)
            and not isinstance(v.get("observed_history_gap_minutes"), bool)
            and v["observed_history_gap_minutes"] >= 0]
    return {
        "stocks_with_observed_history_gaps": sum(n > 0 for n in gaps),
        "stocks_with_insufficient_observed_history": sum(
            v.get("observed_history_insufficient") is True for v in valid),
        "observed_history_gap_minutes_total": sum(gaps),
        "stocks_with_unknown_observed_history": sum(
            v.get("observed_history_order_valid") is False for v in valid),
    }
