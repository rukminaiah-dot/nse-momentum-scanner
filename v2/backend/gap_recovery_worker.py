"""Rate-limited, off-feed-thread Upstox gap recovery.

This worker is deliberately opt-in; scanner integration must protect the
completed/current candle state with a shared lock before enabling it.
"""
import threading
import time
from datetime import datetime
from zoneinfo import ZoneInfo
from .verified_gap_recovery import validated_completed_rows, merge_verified_missing

IST = ZoneInfo("Asia/Kolkata")

class GapRecoveryWorker:
    def __init__(self, fetch_rows, snapshot, merge, *, cooldown=120, max_pending=203):
        """fetch_rows(key), snapshot(key)->(history,active_minute),
        merge(key,recovered,active_minute)->count. Both state callbacks must lock.
        """
        self.fetch_rows = fetch_rows
        self.snapshot = snapshot
        self.merge = merge
        self.cooldown = cooldown
        self.max_pending = max_pending
        self._last_attempt = {}
        self._pending = set()
        self._lock = threading.Lock()

    def request(self, key):
        now = time.monotonic()
        with self._lock:
            if key in self._pending or len(self._pending) >= self.max_pending:
                return False
            if now - self._last_attempt.get(key, float("-inf")) < self.cooldown:
                return False
            self._pending.add(key)
            self._last_attempt[key] = now
        threading.Thread(target=self._run, args=(key,), daemon=True).start()
        return True

    def _run(self, key):
        try:
            history, active_minute = self.snapshot(key)
            if not history or not active_minute:
                return
            rows = self.fetch_rows(key)
            recovered = validated_completed_rows(rows, datetime.now(IST))
            # merge callback must acquire the same lock used by the feed
            # callback and recheck active minute before committing.
            count = self.merge(key, recovered, active_minute)
            print("GAP_RECOVERY:", key, "verified_insertions:", count, flush=True)
        except Exception as exc:
            print("GAP_RECOVERY_FAILED:", key, type(exc).__name__, flush=True)
        finally:
            with self._lock:
                self._pending.discard(key)
