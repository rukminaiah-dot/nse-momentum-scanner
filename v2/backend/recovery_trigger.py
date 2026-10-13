"""Pure fail-closed gate for requesting verified historical gap recovery."""
from datetime import timedelta

ONE_MINUTE = timedelta(minutes=1)

def should_request_recovery(history, active_minute, *, enabled, stock, candle_closed):
    """Detect missing *completed* minutes; never infer or synthesize their OHLCV."""
    if not (enabled and stock and candle_closed and active_minute and history):
        return False
    latest = getattr(history[-1], "timestamp", None)
    if latest is None or latest.date() != active_minute.date():
        return False
    if latest >= active_minute:
        return False
    # A closure can jump directly from 11:40 to active 11:43. Request
    # verification even if only one completed candle exists.
    if active_minute - latest > ONE_MINUTE:
        return True
    if len(history) < 2:
        return False
    previous = getattr(history[-2], "timestamp", None)
    return (
        previous is not None
        and previous.date() == latest.date()
        and latest - previous > ONE_MINUTE
    )
