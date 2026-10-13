"""Rate-limited, off-feed-thread Upstox gap recovery.

This worker is deliberately opt-in; scanner integration must protect the
completed/current candle state with a shared lock before enabling it.
"""
import math
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
        if (not isinstance(max_pending, int) or isinstance(max_pending, bool)
                or max_pending < 1 or not math.isfinite(cooldown) or cooldown <= 0):
            raise ValueError("invalid recovery limits")
        if not math.isfinite(min_request_spacing) or min_request_spacing <= 0:
            raise ValueError('invalid request spacing')
        self.min_request_spacing = min_request_spacing
        self._next_request_at = 0.0
        self.max_pending = max_pending
        self._last_attempt = {}
        self._pending = set()
        self._stats = {"requested": 0, "rejected_pending": 0, "rejected_cooldown": 0,
                       "completed": 0, "failed": 0, "skipped": 0, "verified_insertions": 0}
        self._threads = set()
        self._lock = threading.Lock()

    def request(self, key):
        now = time.monotonic()
        with self._lock:
            if key in self._pending or len(self._pending) >= self.max_pending:
                self._stats["rejected_pending"] += 1
                return False
            if now - self._last_attempt.get(key, float("-inf")) < self.cooldown:
                self._stats["rejected_cooldown"] += 1
                return False
            self._pending.add(key)
            self._last_attempt[key] = now
            self._stats["requested"] += 1
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
                self._stats["requested"] -= 1
            raise
        return True

    def _run(self, key):
        try:
            history, active_minute = self.snapshot(key)
            if not history or not active_minute:
                with self._lock:
                    self._stats["skipped"] += 1
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
            with self._lock:
                self._stats["completed"] += 1
                self._stats["verified_insertions"] += count
            print("GAP_RECOVERY:", key, "verified_insertions:", count, flush=True)
        except Exception as exc:
            with self._lock:
                self._stats["failed"] += 1
            print("GAP_RECOVERY_FAILED:", key, type(exc).__name__, flush=True)
        finally:
            with self._lock:
                self._pending.discard(key)
                self._threads.discard(threading.current_thread())

    def status(self):
        """Thread-safe diagnostics; no credentials or market data exposed."""
        with self._lock:
            return {**self._stats, "pending": len(self._pending)}

    def join(self, timeout=5):
        """Wait for in-flight workers during tests or graceful shutdown."""
        with self._lock:
            threads = list(self._threads)
        # One total deadline, not a fresh timeout for every worker.
        if timeout is not None and (not isinstance(timeout, (int, float))
                                    or isinstance(timeout, bool)
                                    or not math.isfinite(timeout) or timeout < 0):
            raise ValueError("invalid worker join timeout")
        deadline = None if timeout is None else time.monotonic() + timeout
        for thread in threads:
            # request() registers a worker just before thread.start(); a
            # concurrent shutdown can observe it before it has started.
            if thread.ident is None:
                continue
            thread.join(timeout=None if deadline is None else
                        max(0, deadline - time.monotonic()))
