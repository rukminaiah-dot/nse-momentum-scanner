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
                # Preserve same-session preload history when the first live
                # tick arrives. Discard stale/future bars from prior sessions
                # or a malformed preload, without altering the live candle.
                preloaded = self.completed.get(key, [])
                valid = [c for c in preloaded
                         if isinstance(getattr(c, "timestamp", None), datetime)
                         and c.timestamp.tzinfo is None
                         and c.timestamp.date() == minute.date()
                         and c.timestamp < minute]
                if valid:
                    self.completed[key] = sorted(
                        valid, key=lambda c: c.timestamp)[-60:]
                else:
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
                    # Match preload/recovery/finalization retention on the
                    # ordinary live rollover path as well.
                    self.completed[key] = self.completed[key][-60:]
                    if self.log_closed_candles:
                        print("CANDLE_CLOSED", key, closed.__dict__)
            self.current[key] = {"minute": minute, "candle": Candle(price, volume)}
            return closed if item else None
        else:
            item["candle"].update(price, volume)
            return None

    def update_regular_session(self, key, price, timestamp_ms, volume=0):
        """Opt-in gated update: never create candles outside regular hours."""
        from .session_guard import session_tick_action
        with self.lock:
            item = self.current.get(key)
            active = item["minute"] if item else None
            action = session_tick_action(timestamp_ms, active)
            if action == "UPDATE":
                return self._update_locked(key, price, timestamp_ms, volume)
            if action == "FINALIZE_LAST_MINUTE":
                return self.finalize_last_regular_minute(key, timestamp_ms)
            return None

    def finalize_last_regular_minute(self, key, timestamp_ms):
        """Opt-in, idempotent 15:29 candle finalization; never starts a new bar.

        Callers must explicitly invoke this method. Normal update() behavior
        is unchanged until a separately reviewed session gate is integrated.
        """
        from .session_guard import session_tick_action
        with self.lock:
            item = self.current.get(key)
            active = item["minute"] if item else None
            if session_tick_action(timestamp_ms, active) != "FINALIZE_LAST_MINUTE":
                return None
            candle = item["candle"]
            candle.timestamp = active
            self.completed.setdefault(key, []).append(candle)
            self.completed[key] = self.completed[key][-60:]
            self.current.pop(key, None)
            if self.log_closed_candles:
                print("CANDLE_CLOSED_SESSION_END", key, candle.__dict__)
            return candle

    def finalize_verified_session_end(self, key, now_ms, schedule,
                                      start_date, end_date, source, verified,
                                      close_grace_minutes=5):
        """Offline-only explicit-calendar finalization; no timer or feed wiring.

        The caller supplies a verified bounded calendar and current event time.
        Never creates a candle, and repeated calls cannot finalize twice.
        """
        from .session_guard import accepted_calendar_tick_action
        with self.lock:
            item = self.current.get(key)
            active = item["minute"] if item else None
            if accepted_calendar_tick_action(
                    now_ms, active, schedule, start_date, end_date,
                    source, verified, close_grace_minutes) != "FINALIZE_LAST_MINUTE":
                return None
            candle = item["candle"]
            candle.timestamp = active
            self.completed.setdefault(key, []).append(candle)
            self.completed[key] = self.completed[key][-60:]
            self.current.pop(key, None)
            if self.log_closed_candles:
                print("CANDLE_CLOSED_VERIFIED_SESSION_END", key, candle.__dict__)
            return candle

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
