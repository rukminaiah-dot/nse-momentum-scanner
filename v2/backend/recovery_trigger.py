"""Pure fail-closed gate for requesting verified historical gap recovery."""
from datetime import timedelta

ONE_MINUTE = timedelta(minutes=1)

def should_request_recovery(history, active_minute, *, enabled, stock, candle_closed):
    """Detect any missing completed minute in today's retained candle history."""
    if not (enabled and stock and candle_closed and active_minute and history):
        return False
    latest = getattr(history[-1], "timestamp", None)
    if latest is None or latest.date() != active_minute.date():
        return False
    if latest >= active_minute:
        return False
    if active_minute - latest > ONE_MINUTE:
        return True
    # Keep detecting an earlier gap after additional live minutes close, so
    # API failures and pending-queue saturation can be retried after cooldown.
    previous = None
    for candle in history:
        minute = getattr(candle, "timestamp", None)
        if minute is None or minute.date() != active_minute.date():
            previous = None
            continue
        if minute > active_minute or (previous is not None and minute <= previous):
            return False
        if previous is not None and minute - previous > ONE_MINUTE:
            return True
        previous = minute
    return False
