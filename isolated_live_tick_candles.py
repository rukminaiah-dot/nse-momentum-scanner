"""Isolated, read-only LTPC -> CandleManager adapter for Fix 10 testing.

No websocket connection, broker requests, orders, or production scanner wiring.
"""
import math
from datetime import datetime, timezone

from v2.backend.candle_manager import CandleManager


def extract_tick(payload, instrument):
    """Return (price, exchange_epoch_milliseconds) or None; reject bad ticks."""
    if not isinstance(payload, dict):
        return None
    feeds = payload.get("feeds")
    feed = feeds.get(instrument) if isinstance(feeds, dict) else None
    # Upstox V3 LTPC may be directly on the feed or nested in ltpcFeed.
    # Full-mode market feeds can nest the same structure under fullFeed.
    ltpc = None
    if isinstance(feed, dict):
        ltpc = feed.get("ltpc")
        if ltpc is None and isinstance(feed.get("ltpcFeed"), dict):
            ltpc = feed["ltpcFeed"].get("ltpc")
        full = feed.get("fullFeed")
        if ltpc is None and isinstance(full, dict):
            market = full.get("marketFF")
            if isinstance(market, dict):
                ltpc = market.get("ltpc")
    if not isinstance(ltpc, dict):
        return None
    try:
        price = float(ltpc["ltp"])
        raw_ts = ltpc["ltt"]
        if isinstance(raw_ts, bool) or isinstance(raw_ts, float):
            return None
        timestamp = int(raw_ts)
        if not math.isfinite(price) or price <= 0 or timestamp <= 0:
            return None
        # Reject timestamps that Python cannot represent.
        datetime.fromtimestamp(timestamp / 1000, tz=timezone.utc)
    except (KeyError, TypeError, ValueError, OverflowError, OSError):
        return None
    return price, timestamp


class IsolatedTickCandles:
    """One-instrument candle state, kept outside production scanner."""
    def __init__(self, instrument):
        if not instrument:
            raise ValueError("instrument required")
        self.instrument = instrument
        self.manager = CandleManager()
        self.accepted = 0
        self.rejected = 0

    def on_message(self, payload):
        tick = extract_tick(payload, self.instrument)
        if tick is None:
            self.rejected += 1
            return False
        price, timestamp = tick
        self.manager.update(self.instrument, price, timestamp)
        self.accepted += 1
        return True
