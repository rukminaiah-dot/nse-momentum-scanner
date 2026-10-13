"""Rate-limited, off-feed-thread Upstox gap recovery.

This worker is deliberately opt-in; scanner integration must protect the
completed/current candle state with a shared lock before enabling it.
"""
import threading
import time
from datetime import datetime
from zoneinfo import ZoneInfo
from .verified_gap_recovery import validated_completed_rows

IST = ZoneInfo("Asia/Kolkata")

class GapRecoveryWorker:
    def __init__(self, fetch_rows, snapshot, merge, *, cooldown=120, max_pending=4, min_request_spacing=1.0):
        """fetch_rows(key), snapshot(key)->(history,active_minute),
        merge(key,recovered,active_minute)->count. Both state callbacks must lock.
        """
        self.fetch_rows = fetch_rows
        self.snapshot = snapshot
        self.merge = merge
        self.cooldown = cooldown
        if max_pending < 1 or cooldown <= 0:
            raise ValueError("invalid recovery limits")
        if min_request_spacing <= 0:
            raise ValueError('invalid request spacing')
        self.min_request_spacing = min_request_spacing
        self._next_request_at = 0.0
        self.max_pending = max_pending
        self._last_attempt = {}
        self._pending = set()
        self._threads = set()
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
        thread = threading.Thread(target=self._run, args=(key,), daemon=True)
        with self._lock:
            self._threads.add(thread)
        try:
            thread.start()
        except Exception:
            with self._lock:
                self._pending.discard(key)
                self._threads.discard(thread)
                self._last_attempt.pop(key, None)
            raise
        return True

    def _run(self, key):
        try:
            history, active_minute = self.snapshot(key)
            if not history or not active_minute:
                return
            # Reserve a global API slot; never sleep on the websocket thread.
            with self._lock:
                slot = max(time.monotonic(), self._next_request_at)
                self._next_request_at = slot + self.min_request_spacing
            delay = slot - time.monotonic()
            if delay > 0:
                time.sleep(delay)
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
                self._threads.discard(threading.current_thread())

    def join(self, timeout=5):
        """Wait for in-flight workers during tests or graceful shutdown."""
        with self._lock:
            threads = list(self._threads)
        for thread in threads:
            thread.join(timeout=timeout)
