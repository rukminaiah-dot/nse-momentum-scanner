"""Controlled read-only gap acceptance on isolated LIVE-tick candle state.

Only real broker historical candles are used. No fabricated websocket ticks,
orders, production scanner imports, or mutation of broker state.
"""
from datetime import datetime
from zoneinfo import ZoneInfo

from v2.backend.verified_gap_recovery import validated_completed_rows

IST = ZoneInfo("Asia/Kolkata")


def controlled_gap_acceptance(bridge):
    """Return (passed, reason) after a bounded, isolated broker-backed test.

    Requires a genuine websocket tick already ingested by bridge. Seeds one
    historical completed candle as a missing minute in isolated memory, then
    asks the normal off-feed worker to recover it from a SECOND broker fetch.
    A natural websocket gap is a separate, unverified condition.
    """
    manager = bridge.candles.manager
    key = bridge.instrument
    with manager.lock:
        active_item = manager.current.get(key)
        if active_item is None or bridge.candles.accepted < 1:
            return False, "no ingested live tick"
        active = active_item["minute"]
        active_candle = active_item["candle"]
        original = list(manager.completed.get(key, []))
    try:
        rows = bridge.worker.fetch_rows(key)
        validated = validated_completed_rows(rows, datetime.now(IST))
    except Exception:
        return False, "initial authenticated historical fetch failed"
    candidates = sorted(m for m in validated if m.date() == active.date() and m < active)
    if len(candidates) < 2:
        return False, "insufficient same-day completed broker minutes"
    # Use only already authenticated broker candles, strictly before live minute.
    missing = candidates[-2]
    anchors = [validated[m] for m in candidates if m != missing]
    with manager.lock:
        item = manager.current.get(key)
        if item is None or item["minute"] != active or item["candle"] is not active_candle:
            return False, "live minute advanced during setup"
        if any(c.timestamp in candidates for c in manager.completed.get(key, [])):
            return False, "candidate minutes already exist in live history"
        # Preserve all existing live history. Seed only an anchor that really
        # exists at the broker; the omitted minute is the controlled gap.
        manager.completed.setdefault(key, []).extend(anchors)
    try:
        if not bridge.worker.request(key):
            return False, "recovery request rate-limited or pending"
        bridge.worker.join(timeout=5)
        status = bridge.worker.status()
        with manager.lock:
            completed = list(manager.completed.get(key, []))
            current = manager.current.get(key)
        by_minute = {c.timestamp: c for c in completed}
        if status["pending"] or status["failed"] or status["verified_insertions"] != 1:
            return False, "historical recovery not verified"
        if (missing not in by_minute or current is None
                or current["minute"] < active
                or any(c.timestamp not in by_minute for c in original)):
            return False, "isolated candle integrity check failed"
        if by_minute[missing] is not validated[missing]:
            # The second API fetch builds new candle instances: verify OHLCV.
            recovered = by_minute[missing]
            expected = validated[missing]
            if any(getattr(recovered, field) != getattr(expected, field)
                   for field in ("open", "high", "low", "close", "volume")):
                return False, "broker candle values differ"
        return True, "controlled isolated broker-backed gap recovered"
    finally:
        # Never leave synthetic test setup in the live-feed manager.
        # The probe terminates after acceptance; retain any real feed updates.
        with manager.lock:
            seeded = manager.completed.get(key, [])
            manager.completed[key] = [c for c in seeded if all(c is not a for a in anchors)]
