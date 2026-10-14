"""Read-only completeness check for SQLite scanner history vs PostgreSQL archive.

A count match alone does not prove completeness; compare exact observation keys.
This checks only source rows currently available in SQLite. Older lost SQLite
history cannot be reconstructed or verified by this check.
"""
import sqlite3

def compare_archive_keys(sqlite_path, pg_connection):
    """Return exact source/archive key comparison without changing either DB."""
    with sqlite3.connect(sqlite_path, timeout=10) as source:
        source_keys = set(source.execute(
            """SELECT symbol,candle_time FROM scanner_signal_history
               WHERE signal IN ('BUY','SELL','HOLD') AND price IS NOT NULL"""
        ).fetchall())
    archive_keys = set()
    cursor = pg_connection.execute(
        "SELECT symbol,candle_time_ist FROM scanner_signal_archive"
    )
    for symbol, stamp in cursor.fetchall():
        archive_keys.add((symbol, stamp.strftime("%Y-%m-%d %H:%M:%S")
                          if hasattr(stamp, "strftime") else str(stamp)))
    missing = source_keys - archive_keys
    return {
        "status": "MATCHED_AVAILABLE_SOURCE" if not missing else "MISSING_ARCHIVE_ROWS",
        "sqlite_available_observations": len(source_keys),
        "postgres_archive_observations": len(archive_keys),
        "missing_from_archive": len(missing),
        "extra_archive_observations": len(archive_keys - source_keys),
        "historical_completeness_verified": False,
        "note": "Only currently available SQLite observations checked; lost prior history cannot be verified."
    }
