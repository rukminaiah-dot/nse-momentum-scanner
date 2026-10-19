"""Opt-in, fail-open archival of already-persisted scanner observations.

One reusable PostgreSQL connection per process, guarded by a lock.
Disabled unless ENABLE_SIGNAL_ARCHIVE_POSTGRES=1. Schema initialization
remains an explicit manual step. No orders or background jobs.
"""
import os
import threading

_lock = threading.Lock()
_connection = None
_connection_url = None

def close_archive_connection():
    """Explicitly release the cached connection (also useful in tests)."""
    global _connection, _connection_url
    with _lock:
        connection = _connection
        _connection = None
        _connection_url = None
        if connection is not None:
            connection.close()

def archive_observed_signal(symbol, candle_time, price, signal):
    """Persist a signal without allowing PostgreSQL failures to stop scanning."""
    global _connection, _connection_url
    if os.getenv("ENABLE_SIGNAL_ARCHIVE_POSTGRES") != "1":
        return "DISABLED"
    url = os.getenv("DATABASE_URL")
    if not url:
        return "MISSING_DATABASE_URL"
    with _lock:
        try:
            import psycopg
            from .signal_archive_postgres import archive_signal_rows
            if _connection is None or _connection.closed or _connection_url != url:
                if _connection is not None:
                    _connection.close()
                _connection = None
                _connection_url = None
                _connection = psycopg.connect(url, connect_timeout=2)
                _connection_url = url
            archive_signal_rows(_connection, [(symbol, candle_time, price, signal)])
            _connection.commit()
            return "ARCHIVED_OR_ALREADY_PRESENT"
        except Exception as exc:
            print("SIGNAL_ARCHIVE_WRITE_FAILED:", type(exc).__name__, flush=True)
            if _connection is not None:
                try:
                    _connection.close()
                except Exception:
                    pass
            _connection = None
            _connection_url = None
            return "ARCHIVE_FAILED"
