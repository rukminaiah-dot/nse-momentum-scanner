"""Offline timestamp diagnostics. No logging, network, or scanner integration."""
from datetime import datetime
import math
from zoneinfo import ZoneInfo

IST = ZoneInfo("Asia/Kolkata")


def inspect_tick_timestamp(raw_ltt, arrival_ms, *, session_action=None):
    """Return minimal timing metadata without prices, tokens, or full payloads.

    The optional session_action is supplied by a separately verified calendar
    classifier. None means UNKNOWN, never implicitly regular-session.
    """
    if isinstance(raw_ltt, bool) or isinstance(arrival_ms, bool):
        return {"status": "INVALID"}
    try:
        # Reject fractional, non-finite and ambiguous-magnitude timestamps.
        # Epoch seconds are 10 digits; epoch milliseconds are 13 digits for
        # modern trading dates. Do not silently reinterpret other magnitudes.
        event_number = float(raw_ltt)
        arrival_number = float(arrival_ms)
        if (not math.isfinite(event_number) or not math.isfinite(arrival_number)
                or not event_number.is_integer() or not arrival_number.is_integer()):
            return {"status": "INVALID"}
        event_ms = int(event_number)
        arrival_ms = int(arrival_number)
        if 10**9 <= event_ms < 10**10:
            event_ms *= 1000
        elif not 10**12 <= event_ms < 10**13:
            return {"status": "INVALID"}
        if not 10**12 <= arrival_ms < 10**13:
            return {"status": "INVALID"}
        event = datetime.fromtimestamp(event_ms / 1000, IST)
        arrival = datetime.fromtimestamp(arrival_ms / 1000, IST)
    except (TypeError, ValueError, OverflowError, OSError):
        return {"status": "INVALID"}
    skew_ms = arrival_ms - event_ms
    status = ("FUTURE" if skew_ms < -5000 else
              "STALE" if skew_ms > 120000 else "FRESH")
    return {
        "status": status,
        "event_ist": event.isoformat(),
        "arrival_ist": arrival.isoformat(),
        "arrival_minus_event_ms": skew_ms,
        "session_action": session_action if session_action in
            ("UPDATE", "FINALIZE_LAST_MINUTE", "REJECT") else "UNKNOWN",
    }
