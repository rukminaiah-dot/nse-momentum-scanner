"""Pure scanner intraday preload selection model; no API, scanner, or DB imports.

The live scanner selects unique, completed current-session minute candles,
sorts chronologically, and retains the latest 60 when any are available.
Otherwise it falls back to the separately loaded historical candles.
"""
from datetime import datetime


def select_completed_preload(historical, intraday, *, session_date,
                             current_minute, limit=60):
    """Return a new list; never mutate source candles or fetch external data.

    `intraday` contains candles with naive local timestamps already converted
    to the scanner's Asia/Kolkata wall-clock convention.
    """
    if not isinstance(current_minute, datetime):
        raise ValueError("current_minute must be a datetime")
    if not isinstance(limit, int) or isinstance(limit, bool) or limit < 1:
        raise ValueError("limit must be a positive integer")
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
    return current[-limit:] if current else list(historical)
