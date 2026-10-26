"""Single-flight snapshots: HTTP polling must never duplicate expensive scans."""
from threading import Lock, Thread, Semaphore
from time import monotonic


_bulk_scan_slot = Semaphore(1)


class BackgroundSnapshot:
    def __init__(self, ttl):
        self.ttl = ttl
        self.lock = Lock()
        self.result = None
        self.finished_at = 0
        self.running = False
        self.worker = None
        self.last_error = None

    def get(self, build, empty):
        with self.lock:
            if not self.running and (self.finished_at == 0 or monotonic() - self.finished_at >= self.ttl):
                self.running = True
                self.worker = Thread(target=self._refresh, args=(build,), daemon=True)
                self.worker.start()
            result = dict(self.result if self.result is not None else empty)
            result['refreshing'] = self.running
            result['cache_age_seconds'] = (round(monotonic() - self.finished_at, 1)
                                           if self.result is not None else None)
            if self.last_error:
                result['refresh_error'] = self.last_error
            return result

    def _refresh(self, build):
        try:
            with _bulk_scan_slot:
                result = build()
            if not isinstance(result, dict):
                raise ValueError('invalid snapshot')
            with self.lock:
                self.result = result
                self.last_error = None
        except Exception as exc:
            with self.lock:
                self.last_error = type(exc).__name__
        finally:
            with self.lock:
                self.finished_at = monotonic()
                self.running = False
