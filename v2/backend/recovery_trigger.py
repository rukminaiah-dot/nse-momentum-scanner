"""Pure fail-closed gate for requesting verified historical gap recovery."""
from datetime import timedelta

ONE_MINUTE = timedelta(minutes=1)

def should_request_recovery(history, active_minute, *, enabled, stock, candle_closed):
    """Detect missing completed minutes only after validating history order."""
    if not (enabled and stock and candle_closed and active_minute and history):
        return False
    latest = getattr(history[-1], "timestamp", None)
    if latest is None or latest.date() != active_minute.date() or latest >= active_minute:
        return False
    previous = None
    gap = False
    for candle in history:
        minute = getattr(candle, "timestamp", None)
        if minute is None or minute > active_minute:
            return False
        if previous is not None and minute <= previous:
            return False
        if previous is not None and minute.date() == previous.date():
            gap = gap or minute - previous > ONE_MINUTE
        previous = minute
    return gap or active_minute - latest > ONE_MINUTE
