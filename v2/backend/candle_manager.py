import threading
from datetime import datetime
from zoneinfo import ZoneInfo
from .candles import Candle

class CandleManager:
    def __init__(self, *, log_closed_candles=True):
        self.log_closed_candles = log_closed_candles
        self.lock = threading.RLock()
        self.current = {}
        self.completed = {}

    def minute_key(self, ts):
        return datetime.fromtimestamp(float(ts) / 1000, ZoneInfo("Asia/Kolkata")).replace(second=0, microsecond=0, tzinfo=None)

    def update(self, key, price, ts, volume=0):
        with self.lock:
            return self._update_locked(key, price, ts, volume)

    def _update_locked(self, key, price, ts, volume=0):
        minute = self.minute_key(ts)
        item = self.current.get(key)

        # Never roll the active candle backwards on delayed/out-of-order ticks.
        if item is not None and minute < item["minute"]:
            return None
        if item is None or item["minute"] != minute:
            if item is None:
                # A fresh session must not inherit retained bars from an old feed.
                self.completed.pop(key, None)
            closed = None
            if item:
                if item["minute"].date() != minute.date():
                    # A new trading date must not inherit prior-session bars.
                    self.completed.pop(key, None)
                else:
                    closed = item["candle"]
                    closed.timestamp = item["minute"]
                    self.completed.setdefault(key, []).append(closed)
                    if self.log_closed_candles:
                        print("CANDLE_CLOSED", key, closed.__dict__)
            self.current[key] = {"minute": minute, "candle": Candle(price, volume)}
            return closed if item else None
        else:
            item["candle"].update(price, volume)
            return None

    def recovery_snapshot(self, key):
        with self.lock:
            item = self.current.get(key)
            return list(self.completed.get(key, [])), (item["minute"] if item else None)

    def merge_recovered(self, key, recovered, expected_active_minute):
        from .verified_gap_recovery import merge_verified_missing
        with self.lock:
            item = self.current.get(key)
            active = item["minute"] if item else None
            if (active is None or expected_active_minute is None
                    or active < expected_active_minute
                    or active.date() != expected_active_minute.date()):
                return 0
            # The feed may advance while Upstox responds. Verified historical
            # minutes remain safe to insert if still strictly before active.
            merged, added = merge_verified_missing(self.completed.get(key, []), recovered, active_minute=active)
            # Apply retention even when the broker supplied no missing bars.
            # Otherwise an uninterrupted feed can leave completed history
            # unbounded whenever recovery requests are idempotent.
            existing = self.completed.get(key, [])
            if len(merged) != len(existing) or any(
                    a is not b for a, b in zip(merged, existing)):
                self.completed[key] = merged
            return len(added)
