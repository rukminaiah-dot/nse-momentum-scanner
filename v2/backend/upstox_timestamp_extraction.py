"""Offline-only extraction of timing fields from decoded Upstox V3 messages.

Caller supplies local receipt timestamp captured BEFORE any message processing.
No network, filesystem, scanner or order interaction.
"""
from .nonproduction_timestamp_observer import observe_message_timing


def inspect_decoded_message(message, arrival_ms):
    """Return aggregate-safe timing records, without instrument identifiers.

    The optional market-status field is not inferred from undocumented payload
    structures. Unknown remains UNKNOWN until an observed schema is verified.
    """
    if not isinstance(message, dict):
        return []
    feeds = message.get("feeds")
    if not isinstance(feeds, dict):
        return []
    current_ts = message.get("currentTs")
    observations = []
    for feed in feeds.values():
        if not isinstance(feed, dict):
            continue
        ltpc = feed.get("ltpc")
        if not isinstance(ltpc, dict) or not ltpc.get("ltt"):
            ltpc = None
            for container in ("ff", "fullFeed"):
                nested = feed.get(container)
                if not isinstance(nested, dict):
                    continue
                for kind in ("marketFF", "indexFF"):
                    candidate = nested.get(kind)
                    if isinstance(candidate, dict):
                        value = candidate.get("ltpc")
                        if isinstance(value, dict) and value.get("ltt"):
                            ltpc = value
                            break
                if ltpc is not None:
                    break
        if not isinstance(ltpc, dict):
            continue
        observations.append(observe_message_timing(ltpc.get("ltt"), current_ts, arrival_ms))
    return observations
