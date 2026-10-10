"""Research-only expiry momentum signals. No order execution."""

def expiry_signal(ema9, ema20, momentum, index_name=None, now=None):
    """Return WATCH CALL, WATCH PUT, or NO TRADE."""
    from v2.backend.expiry_momentum import expiry_watch_status

    if expiry_watch_status(index_name, now) != "WATCH":
        return "NO TRADE"

    if any(value is None for value in (ema9, ema20, momentum)):
        return "NO TRADE"

    if ema9 > ema20 and momentum > 0:
        return "WATCH CALL"

    if ema9 < ema20 and momentum < 0:
        return "WATCH PUT"

    return "NO TRADE"

def candle_is_fresh(updated_at, now=None):
    """Accept only candles from the last 2 minutes (IST)."""
    from datetime import datetime, timedelta
    from zoneinfo import ZoneInfo

    ist = ZoneInfo("Asia/Kolkata")
    now = now or datetime.now(ist)

    try:
        candle_time = datetime.fromisoformat(updated_at)
        if candle_time.tzinfo is None:
            candle_time = candle_time.replace(tzinfo=ist)

        age = now - candle_time
        return timedelta(0) <= age <= timedelta(minutes=2)
    except (TypeError, ValueError):
        return False
