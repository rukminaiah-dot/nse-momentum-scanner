"""Offline timestamp diagnostics. No logging, network, or scanner integration."""
from datetime import datetime
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
        event_ms = int(float(raw_ltt))
        arrival_ms = int(float(arrival_ms))
        if event_ms < 10**11:
            event_ms *= 1000
        if event_ms <= 0 or arrival_ms <= 0:
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
