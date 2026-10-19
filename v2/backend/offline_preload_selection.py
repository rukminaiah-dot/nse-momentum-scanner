"""Pure scanner intraday preload selection model; no API, scanner, or DB imports.

Select every unique, completed candle from the current session, in chronological
order. If the intraday source has no completed candles, use the historical
warmup list.
"""
from datetime import datetime


def select_completed_preload(historical, intraday, *, session_date,
                             current_minute):
    """Return a new list; never mutate source candles or fetch external data.

    The intraday input contains candles with naive local timestamps already
    converted to the scanner's Asia/Kolkata wall-clock convention.
    """
    if not isinstance(current_minute, datetime):
        raise ValueError("current_minute must be a datetime")
    seen = set()
    current = []
    for candle in intraday:
        stamp = getattr(candle, "timestamp", None)
        if stamp is None or stamp.date() != session_date:
            continue
        if stamp >= current_minute or stamp in seen:
            continue
        seen.add(stamp)
        current.append(candle)
    current.sort(key=lambda candle: candle.timestamp)
    return current if current else list(historical)
