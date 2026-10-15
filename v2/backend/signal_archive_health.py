"""Read-only SQLite vs PostgreSQL signal archive reconciliation.

Only currently available SQLite history can be checked. Previously lost rows
cannot be reconstructed or certified by a successful comparison.
"""
import sqlite3
from datetime import datetime
from math import isfinite

def _timestamp(value):
    return value.isoformat(sep=" ") if isinstance(value, datetime) else str(value)

def compare_archive_keys(sqlite_path, pg_connection):
    """Compare observation keys AND signal/price values without modifying databases."""
    source_rows = {}
    duplicate_source_keys = set()
    source_rows_scanned = 0
    conflicting_source_keys = set()
    with sqlite3.connect(f"file:{sqlite_path}?mode=ro", uri=True, timeout=10) as source:
        for symbol, stamp, price, signal in source.execute(
            """SELECT symbol,candle_time,price,signal FROM scanner_signal_history
               WHERE signal IN ('BUY','SELL','HOLD')"""
        ):
            source_rows_scanned += 1
            if not isinstance(symbol, str) or not symbol.strip() or not isinstance(stamp, str) or not stamp.strip():
                raise ValueError("invalid SQLite signal candle key")
            try:
                parsed = datetime.fromisoformat(stamp)
            except ValueError:
                raise ValueError("invalid SQLite candle timestamp") from None
            if parsed.tzinfo is not None:
                raise ValueError("invalid SQLite candle timestamp; expected naive IST")
            try:
                numeric_price = float(price)
            except (TypeError, ValueError, OverflowError):
                raise ValueError("invalid SQLite signal price") from None
            if not isinstance(price, (int, float)) or not isfinite(numeric_price) or numeric_price <= 0:
                raise ValueError("invalid SQLite signal price")
            key = (symbol, _timestamp(parsed))
            value = (numeric_price, signal)
            if key in source_rows:
                duplicate_source_keys.add(key)
                if source_rows[key] != value:
                    conflicting_source_keys.add(key)
            else:
                source_rows[key] = value
    archive_rows = {}
    duplicate_archive_keys = set()
    archive_rows_scanned = 0
    for symbol, stamp, price, signal in pg_connection.execute(
        "SELECT symbol,candle_time_ist,price,signal FROM scanner_signal_archive"
    ).fetchall():
        archive_rows_scanned += 1
        if not isinstance(symbol, str) or not symbol.strip() or not isinstance(stamp, datetime) or stamp.tzinfo is not None:
            raise ValueError("invalid PostgreSQL archive candle key")
        if signal not in ("BUY", "SELL", "HOLD"):
            raise ValueError("invalid PostgreSQL archive signal")
        try:
            numeric_price = float(price)
        except (TypeError, ValueError, OverflowError):
            raise ValueError("invalid PostgreSQL archive price") from None
        if not isfinite(numeric_price) or numeric_price <= 0:
            raise ValueError("invalid PostgreSQL archive price")
        key = (symbol, _timestamp(stamp))
        if key in archive_rows:
            duplicate_archive_keys.add(key)
        else:
            archive_rows[key] = (numeric_price, signal)
    source_keys, archive_keys = set(source_rows), set(archive_rows)
    missing = source_keys - archive_keys
    mismatched = {
        key for key in source_keys & archive_keys
        if source_rows[key] != archive_rows[key]
    }
    signal_mismatches = {key for key in mismatched if source_rows[key][1] != archive_rows[key][1]}
    price_mismatches = {key for key in mismatched if source_rows[key][0] != archive_rows[key][0]}
    extra = archive_keys - source_keys
    if duplicate_archive_keys:
        status = "DUPLICATE_ARCHIVE_OBSERVATIONS"
    elif conflicting_source_keys:
        status = "CONFLICTING_SQLITE_OBSERVATIONS"
    elif duplicate_source_keys:
        status = "DUPLICATE_SQLITE_OBSERVATIONS"
    elif not source_keys:
        status = "NO_AVAILABLE_SQLITE_OBSERVATIONS"
    elif missing:
        status = "MISSING_ARCHIVE_ROWS"
    elif mismatched:
        status = "MISMATCHED_ARCHIVE_VALUES"
    elif extra:
        status = "MATCHED_AVAILABLE_SOURCE_WITH_EXTRA_ARCHIVE_ROWS"
    else:
        status = "MATCHED_AVAILABLE_SOURCE"
    return {
        "status": status,
        "sqlite_available_observations": len(source_keys),
        "sqlite_source_rows_scanned": source_rows_scanned,
        "duplicate_archive_candle_keys": len(duplicate_archive_keys),
        "duplicate_archive_samples": [
            {"symbol": symbol, "candle_time_ist": stamp}
            for symbol, stamp in sorted(duplicate_archive_keys)[:10]
        ],
        "duplicate_sqlite_candle_keys": len(duplicate_source_keys),
        "conflicting_sqlite_candle_keys": len(conflicting_source_keys),
        "conflicting_sqlite_samples": [
            {"symbol": symbol, "candle_time_ist": stamp}
            for symbol, stamp in sorted(conflicting_source_keys)[:10]
        ],
        "duplicate_sqlite_samples": [
            {"symbol": symbol, "candle_time_ist": stamp}
            for symbol, stamp in sorted(duplicate_source_keys)[:10]
        ],
        "postgres_archive_observations": len(archive_keys),
        "postgres_archive_rows_scanned": archive_rows_scanned,
        "missing_from_archive": len(missing),
        "missing_samples": [
            {"symbol": symbol, "candle_time_ist": stamp}
            for symbol, stamp in sorted(missing)[:10]
        ],
        "mismatched_archive_values": len(mismatched),
        "mismatched_signal_values": len(signal_mismatches),
        "mismatched_price_values": len(price_mismatches),
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
        "available_source_reconciliation_verified": bool(source_keys) and not (missing or mismatched or duplicate_source_keys or duplicate_archive_keys or conflicting_source_keys),
        "historical_completeness_verified": False,
        "verification_scope": "CURRENT_SQLITE_ROWS_ONLY",
        "historical_audit_status": "NOT_VERIFIABLE_FROM_CURRENT_SQLITE",
        "note": "Only currently available SQLite observations checked; lost prior history cannot be verified."
    }
