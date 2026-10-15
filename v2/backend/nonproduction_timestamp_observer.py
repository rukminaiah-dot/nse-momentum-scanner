"""Read-only timestamp observer for isolated, nonproduction feed consumers.

No feed connection, scanner mutation, filesystem writes, or raw payload retention.
Caller must explicitly supply arrival time captured at message receipt.
"""
from collections import Counter
from datetime import datetime
from zoneinfo import ZoneInfo

from .timestamp_audit import inspect_tick_timestamp

IST = ZoneInfo("Asia/Kolkata")


def observe_ltt(raw_ltt, arrival_ms):
    """Return redacted timing metadata; never infer calendar validity."""
    result = inspect_tick_timestamp(raw_ltt, arrival_ms)
    if result["status"] == "INVALID":
        return {"status": "INVALID", "session": "UNKNOWN"}
    event = datetime.fromisoformat(result["event_ist"])
    arrival = datetime.fromisoformat(result["arrival_ist"])
    hour_minute = event.hour * 60 + event.minute
    # Time-of-day labels are illustrative, NOT official NSE calendar decisions.
    window = ("BEFORE_REGULAR_HOURS" if hour_minute < 9 * 60 + 15 else
              "AFTER_REGULAR_HOURS" if hour_minute >= 15 * 60 + 30 else
              "WITHIN_REGULAR_HOURS")
    return {
        "status": result["status"],
        "event_ist": event.isoformat(),
        "arrival_ist": arrival.isoformat(),
        "arrival_minus_event_ms": result["arrival_minus_event_ms"],
        "regular_hours_window": window,
        "session": "UNKNOWN",
    }


class TimestampObserver:
    """Bounded aggregate-only observer; no identifiers, prices or raw ticks."""

    def __init__(self):
        self.counts = Counter()

    def record(self, raw_ltt, arrival_ms):
        observation = observe_ltt(raw_ltt, arrival_ms)
        self.counts[(observation["status"],
                     observation.get("regular_hours_window", "UNKNOWN"))] += 1
        return observation

    def summary(self):
        return [
            {"status": status, "regular_hours_window": window, "count": count}
            for (status, window), count in sorted(self.counts.items())
        ]
