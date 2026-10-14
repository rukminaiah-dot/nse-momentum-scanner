"""Bounded, explicit-start, best-effort async archive delivery.

No worker starts on import. Caller must opt in and start explicitly.
Queue overflow is observable and must never block scanner signals.
"""
import queue
import threading

class SignalArchiveQueue:
    def __init__(self, deliver, *, max_pending=512):
        if not isinstance(max_pending, int) or isinstance(max_pending, bool) or max_pending < 1:
            raise ValueError("max_pending must be positive")
        self.deliver = deliver
        self.pending = queue.Queue(maxsize=max_pending)
        self._thread = None
        self._lock = threading.Lock()
        self.accepted = 0
        self.dropped = 0
        self.failed = 0
        self.delivered = 0

    def start(self):
        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                return
            self._thread = threading.Thread(target=self._run, daemon=True, name="signal-archive")
            self._thread.start()

    def submit(self, row):
        try:
            self.pending.put_nowait(row)
        except queue.Full:
            with self._lock:
                self.dropped += 1
            return False
        with self._lock:
            self.accepted += 1
        return True

    def _run(self):
        while True:
            row = self.pending.get()
            try:
                if row is None:
                    return
                status = self.deliver(*row)
                with self._lock:
                    if status == "ARCHIVED_OR_ALREADY_PRESENT":
                        self.delivered += 1
                    else:
                        self.failed += 1
            except Exception:
                with self._lock:
                    self.failed += 1
            finally:
                self.pending.task_done()

    def status(self):
        with self._lock:
            return {"accepted": self.accepted, "delivered": self.delivered,
                    "failed": self.failed, "dropped": self.dropped,
                    "pending": self.pending.qsize(),
                    "running": self._thread is not None and self._thread.is_alive()}
