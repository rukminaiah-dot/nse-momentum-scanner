"""Daily NIFTY valuation history from the durable/local snapshot archive."""
from __future__ import annotations

import os
import sqlite3
from typing import Any

from .database import DB_PATH


def _record_tuple(record: dict[str, Any]) -> tuple[Any, ...]:
    return (
        str(record["session_date"]), float(record["value"]),
        str(record["as_of"]), str(record["fetched_at"]),
        str(record["source"]), str(record.get("basis") or ""),
    )


def _save_postgres(values: tuple[Any, ...]) -> bool:
    url = os.environ.get("DATABASE_URL")
    if not url:
        return False
    import psycopg
    with psycopg.connect(url, connect_timeout=3) as db:
        db.execute("""
            CREATE TABLE IF NOT EXISTS daily_nifty_valuations (
                session_date DATE PRIMARY KEY,
                pe DOUBLE PRECISION NOT NULL,
                source_as_of TEXT NOT NULL,
                fetched_at TIMESTAMPTZ NOT NULL,
                source TEXT NOT NULL,
                basis TEXT NOT NULL DEFAULT ''
            )
        """)
        db.execute("""
            INSERT INTO daily_nifty_valuations(session_date, pe, source_as_of, fetched_at, source, basis)
            VALUES (%s, %s, %s, %s, %s, %s)
            ON CONFLICT (session_date) DO UPDATE SET
                pe = EXCLUDED.pe,
                source_as_of = EXCLUDED.source_as_of,
                fetched_at = EXCLUDED.fetched_at,
                source = EXCLUDED.source,
                basis = EXCLUDED.basis
        """, values)
    return True


def _save_sqlite(values: tuple[Any, ...]) -> None:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(DB_PATH, timeout=5) as db:
        db.execute("""
            CREATE TABLE IF NOT EXISTS daily_nifty_valuations (
                session_date TEXT PRIMARY KEY,
                pe REAL NOT NULL,
                source_as_of TEXT NOT NULL,
                fetched_at TEXT NOT NULL,
                source TEXT NOT NULL,
                basis TEXT NOT NULL DEFAULT ''
            )
        """)
        db.execute("""
            INSERT INTO daily_nifty_valuations(session_date, pe, source_as_of, fetched_at, source, basis)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(session_date) DO UPDATE SET
                pe=excluded.pe, source_as_of=excluded.source_as_of,
                fetched_at=excluded.fetched_at, source=excluded.source, basis=excluded.basis
        """, values)


def save_daily_nifty_pe(record: dict[str, Any]) -> str:
    """Persist one verified daily reading and return the storage path used."""
    values = _record_tuple(record)
    postgres_saved = False
    try:
        postgres_saved = _save_postgres(values)
    except Exception:
        postgres_saved = False
    _save_sqlite(values)
    return "POSTGRESQL_AND_LOCAL" if postgres_saved else "LOCAL_FALLBACK"


def _row_record(row: Any) -> dict[str, Any]:
    return {"session_date": row[0].isoformat() if hasattr(row[0], "isoformat") else str(row[0]),
            "value": float(row[1]), "as_of": row[2],
            "fetched_at": row[3].isoformat() if hasattr(row[3], "isoformat") else row[3],
            "source": row[4], "basis": row[5]}


def _read_history_postgres(limit: int) -> list[dict[str, Any]]:
    url = os.environ.get("DATABASE_URL")
    if not url:
        return []
    import psycopg
    with psycopg.connect(url, connect_timeout=3) as db:
        rows = db.execute("""
            SELECT session_date, pe, source_as_of, fetched_at, source, basis
            FROM daily_nifty_valuations ORDER BY session_date DESC LIMIT %s
        """, (limit,)).fetchall()
    return [_row_record(row) for row in reversed(rows)]


def _read_history_sqlite(limit: int) -> list[dict[str, Any]]:
    with sqlite3.connect(DB_PATH, timeout=3) as db:
        exists = db.execute("""
            SELECT 1 FROM sqlite_master WHERE type='table' AND name='daily_nifty_valuations'
        """).fetchone()
        if not exists:
            return []
        rows = db.execute("""
            SELECT session_date, pe, source_as_of, fetched_at, source, basis
            FROM daily_nifty_valuations ORDER BY session_date DESC LIMIT ?
        """, (limit,)).fetchall()
    return [_row_record(row) for row in reversed(rows)]


def read_nifty_pe_history(limit: int = 6) -> tuple[list[dict[str, Any]], str]:
    """Return recent verified daily records, oldest first, with storage provenance."""
    try:
        requested = max(1, min(60, int(limit)))
    except (TypeError, ValueError, OverflowError):
        requested = 6
    if os.environ.get("DATABASE_URL"):
        try:
            rows = _read_history_postgres(requested)
            if rows:
                return rows, "POSTGRESQL"
        except Exception:
            pass
    try:
        rows = _read_history_sqlite(requested)
        return rows, "LOCAL_FALLBACK" if rows else "UNAVAILABLE"
    except (sqlite3.Error, OSError):
        return [], "UNAVAILABLE"


def _read_postgres() -> dict[str, Any] | None:
    url = os.environ.get("DATABASE_URL")
    if not url:
        return None
    import psycopg
    with psycopg.connect(url, connect_timeout=3) as db:
        row = db.execute("""
            SELECT session_date, pe, source_as_of, fetched_at, source, basis
            FROM daily_nifty_valuations ORDER BY session_date DESC LIMIT 1
        """).fetchone()
    return _row_record(row) if row else None


def _read_sqlite() -> dict[str, Any] | None:
    with sqlite3.connect(DB_PATH, timeout=3) as db:
        exists = db.execute("""
            SELECT 1 FROM sqlite_master WHERE type='table' AND name='daily_nifty_valuations'
        """).fetchone()
        if not exists:
            return None
        row = db.execute("""
            SELECT session_date, pe, source_as_of, fetched_at, source, basis
            FROM daily_nifty_valuations ORDER BY session_date DESC LIMIT 1
        """).fetchone()
    return _row_record(row) if row else None


def read_latest_nifty_pe() -> tuple[dict[str, Any] | None, str]:
    """Return the newest saved valuation, preferring the durable archive."""
    if os.environ.get("DATABASE_URL"):
        try:
            value = _read_postgres()
            if value:
                return value, "POSTGRESQL"
        except Exception:
            pass
    try:
        value = _read_sqlite()
        return (value, "LOCAL_FALLBACK") if value else (None, "UNAVAILABLE")
    except (sqlite3.Error, OSError):
        return None, "UNAVAILABLE"
