"""Verified completed-minute recovery helpers. Opt-in integration only.

Caller must fetch Upstox intraday rows off the websocket callback thread and
serialize merges with candle updates. Never synthesize missing minutes.
"""
from datetime import datetime
from zoneinfo import ZoneInfo
from .candles import Candle

IST = ZoneInfo("Asia/Kolkata")

def validated_completed_rows(rows, now_ist):
    """Return completed same-day Upstox OHLCV candles, or raise on bad data."""
    if now_ist.tzinfo is None or now_ist.utcoffset() is None:
        raise ValueError("current time timezone missing")
    cutoff = now_ist.astimezone(IST).replace(second=0, microsecond=0, tzinfo=None)
    session = cutoff.date()
    result = {}
    for row in rows:
        if len(row) < 6:
            raise ValueError("incomplete Upstox candle")
        stamp = datetime.fromisoformat(str(row[0]))
        if stamp.tzinfo is None:
            raise ValueError("candle timezone missing")
        minute = stamp.astimezone(IST).replace(tzinfo=None)
        if minute.date() != session or minute >= cutoff:
            continue
        if minute.second or minute.microsecond or minute in result:
            raise ValueError("invalid or duplicate candle minute")
        o, h, l, c, v = (float(x) for x in row[1:6])
        from math import isfinite
        if not all(isfinite(x) for x in (o, h, l, c, v)):
            raise ValueError("non-finite candle value")
        if min(o, h, l, c) <= 0 or v < 0 or h < max(o, c, l) or l > min(o, c, h):
            raise ValueError("invalid OHLCV")
        candle = Candle(o, v)
        candle.open, candle.high, candle.low, candle.close = o, h, l, c
        candle.timestamp = minute
        result[minute] = candle
    return result

def merge_verified_missing(existing, recovered, active_minute=None, limit=60):
    """Insert only absent completed minutes; never overwrite live candles."""
    by_minute = {c.timestamp: c for c in existing}
    added = []
    for minute, candle in sorted(recovered.items()):
        if getattr(candle, "timestamp", None) != minute:
            raise ValueError("recovered candle timestamp mismatch")
        if (active_minute is not None and
                (minute.date() != active_minute.date() or minute >= active_minute)):
            continue
        if minute in by_minute:
            continue
        by_minute[minute] = candle
        added.append(minute)
    if limit < 1:
        raise ValueError("invalid history limit")
    retained_minutes = sorted(by_minute)[-limit:]
    retained = set(retained_minutes)
    return [by_minute[t] for t in retained_minutes], [t for t in added if t in retained]
