"""Pure fail-closed gate for requesting verified historical gap recovery."""
from datetime import timedelta

def should_request_recovery(history, active_minute, *, enabled, stock, candle_closed):
    if not (enabled and stock and candle_closed and active_minute and len(history) >= 2):
        return False
    left, right = history[-2:]
    first = getattr(left, "timestamp", None)
    second = getattr(right, "timestamp", None)
    if first is None or second is None:
        return False
    if first.date() != second.date() or second.date() != active_minute.date():
        return False
    return second < active_minute and second - first > timedelta(minutes=1)
