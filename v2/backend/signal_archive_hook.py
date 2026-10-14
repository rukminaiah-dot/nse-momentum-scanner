"""Opt-in, fail-open archival of one already-persisted scanner observation.

Disabled unless ENABLE_SIGNAL_ARCHIVE_POSTGRES=1. The PostgreSQL schema must
be explicitly initialized first. Never places orders or changes signals.
"""
import os

def archive_observed_signal(symbol, candle_time, price, signal):
    if os.getenv("ENABLE_SIGNAL_ARCHIVE_POSTGRES") != "1":
        return "DISABLED"
    url = os.getenv("DATABASE_URL")
    if not url:
        return "MISSING_DATABASE_URL"
    try:
        import psycopg
        from .signal_archive_postgres import archive_signal_rows
        with psycopg.connect(url, connect_timeout=2) as connection:
            archive_signal_rows(connection, [(symbol, candle_time, price, signal)])
        return "ARCHIVED_OR_ALREADY_PRESENT"
    except Exception as exc:
        # Do not log URLs, credentials, or connection error messages.
        print("SIGNAL_ARCHIVE_WRITE_FAILED:", type(exc).__name__, flush=True)
        return "ARCHIVE_FAILED"
