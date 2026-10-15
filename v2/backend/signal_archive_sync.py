"""Explicit SQLite -> PostgreSQL scanner observation sync.

Does not run on import, start any scheduler, create tables, or place orders.
Caller must first initialize the archive with init_signal_archive().
"""
import sqlite3
from datetime import datetime

from .signal_archive_postgres import archive_signal_rows

def sync_observed_signals(sqlite_path, pg_connection, *, batch_size=500):
    """Stream actual persisted scanner rows to PostgreSQL in bounded batches.

    Idempotency is enforced by the PostgreSQL archive's unique candle key.
    Returns (scanned_rows, newly_inserted_rows). Caller owns transaction.
    """
    if not isinstance(batch_size, int) or isinstance(batch_size, bool) or batch_size < 1:
        raise ValueError("batch_size must be a positive integer")
    scanned = inserted = 0
    with sqlite3.connect(f"file:{sqlite_path}?mode=ro", uri=True, timeout=10) as source:
        duplicates = source.execute(
            """SELECT symbol,candle_time FROM scanner_signal_history
               WHERE signal IN ('BUY','SELL','HOLD') AND price IS NOT NULL
               GROUP BY symbol,candle_time HAVING COUNT(*) > 1 LIMIT 1"""
        ).fetchone()
        if duplicates is not None:
            raise ValueError("duplicate SQLite candle keys; resolve before manual archive sync")
        invalid = source.execute(
            """SELECT symbol,candle_time FROM scanner_signal_history
               WHERE signal IN ('BUY','SELL','HOLD')
                 AND (price IS NULL OR typeof(price) NOT IN ('integer','real')
                      OR price <= 0 OR price > 1e308)
               LIMIT 1"""
        ).fetchone()
        if invalid is not None:
            raise ValueError("invalid SQLite signal price; resolve before manual archive sync")
        cursor = source.execute(
            """SELECT symbol,candle_time,price,signal
               FROM scanner_signal_history
               WHERE signal IN ('BUY','SELL','HOLD')
                 AND price IS NOT NULL
               ORDER BY candle_time,symbol"""
        )
        while True:
            rows = cursor.fetchmany(batch_size)
            if not rows:
                break
            inserted += archive_signal_rows(pg_connection, rows)
            scanned += len(rows)
    return {"observations_scanned": scanned,
            "observations_inserted": inserted,
            "observations_already_present": scanned - inserted,
            "mode": "EXPLICIT_READ_ONLY_SOURCE_SYNC",
            "existing_values_overwritten": False,
            "existing_value_matches_verified": False,
            "next_step": "Run manual verify to detect mismatched price/signal values; sync does not repair conflicts."}
