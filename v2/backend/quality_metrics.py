"""Pure observed-history gap metrics; no external data or candle mutation."""
from datetime import timedelta

ONE_MINUTE = timedelta(minutes=1)


def observed_history_gaps(history, today):
    """Count missing minutes strictly between retained same-day candle timestamps.

    This does not claim full-session coverage; missing leading/trailing minutes
    cannot be inferred. Invalid ordering returns an unknown gap count.
    """
    minutes = [
        c.timestamp for c in history
        if getattr(c, "timestamp", None) is not None
        and c.timestamp.date() == today
    ]
    ordered = all(b > a for a, b in zip(minutes, minutes[1:]))
    if not ordered:
        return {"observed_history_gap_minutes": None,
                "observed_history_candles_today": len(minutes),
                "observed_history_order_valid": False}
    gaps = sum(
        int((b - a) / ONE_MINUTE) - 1
        for a, b in zip(minutes, minutes[1:])
        if b - a > ONE_MINUTE
    )
    return {"observed_history_gap_minutes": gaps,
            "observed_history_candles_today": len(minutes),
            "observed_history_order_valid": True}
