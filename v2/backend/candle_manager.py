from copy import copy
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
            return [copy(candle) for candle in self.completed.get(key, [])], (
                active["minute"] if active is not None else None)

    def preload_completed(self, key, candles):
        """Atomically replace startup history; caller must establish preload policy.

        This is a synchronization primitive, not permission to overwrite
        concurrent live data. Integration must enforce startup-only usage.
        """
        with self._state_lock:
            if key in self.current:
                raise RuntimeError("cannot preload after live candle started")
            self.completed[key] = [copy(candle) for candle in candles]

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
            original_minutes = set(by_minute)
            for minute, candle in sorted(recovered.items()):
                if minute.date() != boundary.date() or minute >= boundary:
                    continue
                if minute in by_minute:
                    continue
                # Do not retain a mutable Candle owned by the recovery caller.
                by_minute[minute] = copy(candle)
            # Recovery must not evict live/preloaded history used for indicators.\n            # Keep every existing minute; cap only the recovered candidates.\n            recovered_minutes = sorted(minute for minute in by_minute\n                                       if minute not in original_minutes)[-limit:]\n            retained = sorted(original_minutes.union(recovered_minutes))
            if not any(minute in recovered and minute not in original_minutes
                       for minute in retained):
                return 0
            self.completed[key] = [by_minute[t] for t in retained]
            return sum(1 for minute in retained
                       if minute in recovered and minute not in original_minutes)

    def merge_verified_recovery(self, key, recovered, snapshot_active_minute):
        """Adapter for GapRecoveryWorker.merge(key, recovered, active_minute).

        A worker snapshot is only a hint: update and insertion serialize on
        the same lock, and insertion always checks the latest active minute.
        Never accept a recovery result for a different trading session.
        """
        with self._state_lock:
            active = self.current.get(key)
            if (active is None or snapshot_active_minute is None
                    or active["minute"] < snapshot_active_minute
                    or active["minute"].date() != snapshot_active_minute.date()):
                return 0
            return self.insert_missing_completed(key, recovered)

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
            closed = None
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
