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
    if not isinstance(now_ist, datetime):
        raise ValueError("current time must be datetime")
    if now_ist.tzinfo is None or now_ist.utcoffset() is None:
        raise ValueError("current time timezone missing")
    cutoff = now_ist.astimezone(IST).replace(second=0, microsecond=0, tzinfo=None)
    session = cutoff.date()
    if not isinstance(rows, (list, tuple)):
        raise ValueError("invalid Upstox candle batch")
    result = {}
    for row in rows:
        if not isinstance(row, (list, tuple)):
            raise ValueError("invalid Upstox candle row")
        if len(row) < 6:
            raise ValueError("incomplete Upstox candle")
        if not isinstance(row[0], str):
            raise ValueError("invalid candle timestamp type")
        stamp = datetime.fromisoformat(row[0])
        if stamp.tzinfo is None or stamp.utcoffset() is None:
            raise ValueError("candle timezone missing")
        minute = stamp.astimezone(IST).replace(tzinfo=None)
        if minute.date() != session or minute >= cutoff:
            continue
        # Intraday recovery must not import off-session rows as market candles.
        # NSE regular equity session: 09:15 inclusive to 15:30 exclusive IST.
        if not (9 * 60 + 15 <= minute.hour * 60 + minute.minute < 15 * 60 + 30):
            continue
        if minute.second or minute.microsecond or minute in result:
            raise ValueError("invalid or duplicate candle minute")
        if any(isinstance(value, bool) for value in row[1:6]):
            raise ValueError("boolean OHLCV value")
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
    if isinstance(limit, bool) or not isinstance(limit, int) or limit < 1:
        raise ValueError("invalid history limit")
    by_minute = {c.timestamp: c for c in existing
                 if active_minute is None or (
                     c.timestamp.date() == active_minute.date()
                     and c.timestamp < active_minute)}
    added = []
    for minute, candle in sorted(recovered.items()):
        if getattr(candle, "timestamp", None) != minute:
            raise ValueError("recovered candle timestamp mismatch")
        # Never introduce a candle from another session or at/after the
        # live minute. Callers must provide an active-minute boundary.
        if (active_minute is None or minute.date() != active_minute.date()
                or minute >= active_minute):
            continue
        if minute in by_minute:
            continue
        by_minute[minute] = candle
        added.append(minute)
    retained_minutes = sorted(by_minute)[-limit:]
    retained = set(retained_minutes)
    return [by_minute[t] for t in retained_minutes], [t for t in added if t in retained]
