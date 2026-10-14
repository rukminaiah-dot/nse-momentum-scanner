"""Read-only SQLite vs PostgreSQL signal archive reconciliation.

Only currently available SQLite history can be checked. Previously lost rows
cannot be reconstructed or certified by a successful comparison.
"""
import sqlite3

def _timestamp(value):
    return value.strftime("%Y-%m-%d %H:%M:%S") if hasattr(value, "strftime") else str(value)

def compare_archive_keys(sqlite_path, pg_connection):
    """Compare observation keys AND signal/price values without modifying databases."""
    with sqlite3.connect(sqlite_path, timeout=10) as source:
        source_rows = {
            (symbol, _timestamp(stamp)): (float(price), signal)
            for symbol, stamp, price, signal in source.execute(
                """SELECT symbol,candle_time,price,signal FROM scanner_signal_history
                   WHERE signal IN ('BUY','SELL','HOLD') AND price IS NOT NULL"""
            )
        }
    archive_rows = {
        (symbol, _timestamp(stamp)): (float(price), signal)
        for symbol, stamp, price, signal in pg_connection.execute(
            "SELECT symbol,candle_time_ist,price,signal FROM scanner_signal_archive"
        ).fetchall()
    }
    source_keys, archive_keys = set(source_rows), set(archive_rows)
    missing = source_keys - archive_keys
    mismatched = {
        key for key in source_keys & archive_keys
        if source_rows[key] != archive_rows[key]
    }
    extra = archive_keys - source_keys
    if missing:
        status = "MISSING_ARCHIVE_ROWS"
    elif mismatched:
        status = "MISMATCHED_ARCHIVE_VALUES"
    else:
        status = "MATCHED_AVAILABLE_SOURCE"
    return {
        "status": status,
        "sqlite_available_observations": len(source_keys),
        "postgres_archive_observations": len(archive_keys),
        "missing_from_archive": len(missing),
        "mismatched_archive_values": len(mismatched),
        "extra_archive_observations": len(extra),
        "historical_completeness_verified": False,
        "note": "Only currently available SQLite observations checked; lost prior history cannot be verified."
    }
