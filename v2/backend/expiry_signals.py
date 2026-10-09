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
