"""Read-only SQLite vs PostgreSQL signal archive reconciliation.

Only currently available SQLite history can be checked. Previously lost rows
cannot be reconstructed or certified by a successful comparison.
"""
import sqlite3

def _timestamp(value):
    return value.strftime("%Y-%m-%d %H:%M:%S") if hasattr(value, "strftime") else str(value)

def compare_archive_keys(sqlite_path, pg_connection):
    """Compare observation keys AND signal/price values without modifying databases."""
    with sqlite3.connect(f"file:{sqlite_path}?mode=ro", uri=True, timeout=10) as source:
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
    if not source_keys:
        status = "NO_AVAILABLE_SQLITE_OBSERVATIONS"
    elif missing:
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
        "missing_samples": [
            {"symbol": symbol, "candle_time_ist": stamp}
            for symbol, stamp in sorted(missing)[:10]
        ],
        "mismatched_archive_values": len(mismatched),
        "mismatched_samples": [
            {"symbol": symbol, "candle_time_ist": stamp,
             "sqlite_signal": source_rows[(symbol, stamp)][1],
             "postgres_signal": archive_rows[(symbol, stamp)][1],
             "sqlite_price": source_rows[(symbol, stamp)][0],
             "postgres_price": archive_rows[(symbol, stamp)][0]}
            for symbol, stamp in sorted(mismatched)[:10]
        ],
        "extra_archive_observations": len(extra),
        "extra_archive_samples": [
            {"symbol": symbol, "candle_time_ist": stamp}
            for symbol, stamp in sorted(extra)[:10]
        ],
        "extra_archive_interpretation": (
            "Archive-only rows may be valid retained history absent from current SQLite; "
            "they are not automatically treated as corruption."
        ),
        "available_source_reconciliation_verified": bool(source_keys) and not (missing or mismatched),
        "historical_completeness_verified": False,
        "verification_scope": "CURRENT_SQLITE_ROWS_ONLY",
        "historical_audit_status": "NOT_VERIFIABLE_FROM_CURRENT_SQLITE",
        "note": "Only currently available SQLite observations checked; lost prior history cannot be verified."
    }
