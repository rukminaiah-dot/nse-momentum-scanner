from datetime import datetime
from threading import RLock
from zoneinfo import ZoneInfo
from .candles import Candle

class CandleManager:
    def __init__(self):
        self._state_lock = RLock()
        self.current = {}
        self.completed = {}

    def minute_key(self, ts):
        return datetime.fromtimestamp(float(ts) / 1000, ZoneInfo("Asia/Kolkata")).replace(second=0, microsecond=0, tzinfo=None)

    def snapshot(self, key):
        """Atomically copy completed history and the current active minute."""
        with self._state_lock:
            active = self.current.get(key)
            return list(self.completed.get(key, [])), (
                active["minute"] if active is not None else None)

    def insert_missing_completed(self, key, recovered, limit=60):
        """Repair history only; never emit a candle-closed event or signal.

        Re-read the active minute under the update lock. Missing or invalid
        active state means no recovery, never a best-effort insertion.
        """
        if isinstance(limit, bool) or not isinstance(limit, int) or limit < 1:
            raise ValueError("invalid history limit")
        with self._state_lock:
            active = self.current.get(key)
            if active is None:
                return 0
            boundary = active["minute"]
            existing = self.completed.get(key, [])
            by_minute = {c.timestamp: c for c in existing}
            # Validate the whole batch before touching shared history.
            for minute, candle in recovered.items():
                if getattr(candle, "timestamp", None) != minute:
                    raise ValueError("recovered candle timestamp mismatch")
            inserted = 0
            for minute, candle in sorted(recovered.items()):
                if minute.date() != boundary.date() or minute >= boundary:
                    continue
                if minute in by_minute:
                    continue
                by_minute[minute] = candle
                inserted += 1
            self.completed[key] = [by_minute[t] for t in sorted(by_minute)[-limit:]]
            return inserted

    def update(self, key, price, ts, volume=0):
        with self._state_lock:
            return self._update_locked(key, price, ts, volume)

    def _update_locked(self, key, price, ts, volume=0):
        minute = self.minute_key(ts)
        item = self.current.get(key)

        # Never roll the active candle backwards on delayed/out-of-order ticks.
        if item is not None and minute < item["minute"]:
            return None
        if item is None or item["minute"] != minute:
            if item:
                closed = item["candle"]
                closed.timestamp = item["minute"]
                self.completed.setdefault(key, []).append(closed)
                print("CANDLE_CLOSED", key, closed.__dict__)
            self.current[key] = {"minute": minute, "candle": Candle(price, volume)}
            return closed if item else None
        else:
            item["candle"].update(price, volume)
            return None
