"""Explicit, read-only PostgreSQL signal-history archival helpers.

No background jobs, broker calls, order placement, or automatic migrations.
Call init_signal_archive() deliberately before archive_signal_rows().
"""
from datetime import datetime
from zoneinfo import ZoneInfo

DDL = """
CREATE TABLE IF NOT EXISTS scanner_signal_archive (
    symbol TEXT NOT NULL,
    candle_time_ist TIMESTAMP WITHOUT TIME ZONE NOT NULL,
    price DOUBLE PRECISION NOT NULL CHECK (price > 0),
    signal TEXT NOT NULL CHECK (signal IN ('BUY','SELL','HOLD')),
    recorded_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (symbol, candle_time_ist)
);
CREATE INDEX IF NOT EXISTS idx_scanner_signal_archive_time
    ON scanner_signal_archive(candle_time_ist);
"""

def init_signal_archive(connection):
    """Explicit schema initialization on an already-authorized connection."""
    connection.execute(DDL)

def archive_signal_rows(connection, rows):
    """Idempotently archive observed (symbol, naive IST candle time, price, signal).

    Replays must not overwrite a previously recorded signal.
    Returns number of newly inserted observations.
    """
    from math import isfinite
    inserted = 0
    for symbol, stamp, price, side in rows:
        if isinstance(stamp, str):
            stamp = datetime.fromisoformat(stamp)
        if not isinstance(stamp, datetime) or stamp.tzinfo is not None:
            raise ValueError("candle time must be naive IST datetime")
        if not isinstance(symbol, str) or not symbol.strip():
            raise ValueError("symbol required")
        if side not in ("BUY", "SELL", "HOLD"):
            raise ValueError("invalid signal")
        price = float(price)
        if not isfinite(price) or price <= 0:
            raise ValueError("invalid price")
        result = connection.execute(
            """INSERT INTO scanner_signal_archive
               (symbol,candle_time_ist,price,signal)
               VALUES (%s,%s,%s,%s)
               ON CONFLICT (symbol,candle_time_ist) DO NOTHING
               RETURNING symbol""",
            (symbol, stamp, price, side))
        inserted += int(result.fetchone() is not None)
    return inserted

def fetch_archive_day(connection, day):
    """Return real archived readings for a calendar day in IST."""
    from datetime import date, timedelta
    day = date.fromisoformat(day) if isinstance(day, str) else day
    following = day + timedelta(days=1)
    return connection.execute(
        """SELECT symbol,candle_time_ist,price,signal
           FROM scanner_signal_archive
           WHERE candle_time_ist >= %s AND candle_time_ist < %s
           ORDER BY candle_time_ist,symbol""",
        (datetime.combine(day, datetime.min.time()),
         datetime.combine(following, datetime.min.time()))).fetchall()
