"""Lazy, opt-in scanner archive dispatch. No worker runs unless a signal is submitted.

Best effort only: after a crash or delivery failure, run manual SQLite sync
and verify while the local SQLite source still exists.
"""
import threading
from .signal_archive_queue import SignalArchiveQueue

_dispatch_lock = threading.Lock()
_dispatcher = None

def submit_observation(row):
    global _dispatcher
    with _dispatch_lock:
        if _dispatcher is None:
            from .signal_archive_hook import archive_observed_signal
            _dispatcher = SignalArchiveQueue(archive_observed_signal, max_pending=512)
            _dispatcher.start()
        dispatcher = _dispatcher
    return dispatcher.submit(row)

def archive_queue_status():
    with _dispatch_lock:
        dispatcher = _dispatcher
    if dispatcher is None:
        return {"started": False, "pending": 0, "dropped": 0, "failed": 0}
    return {"started": True, **dispatcher.status()}
