"""Optional PostgreSQL archive for completed index snapshots; no trade execution."""
import os
from datetime import datetime
from zoneinfo import ZoneInfo

INDEX_NAMES = ("NIFTY 50", "SENSEX")


def save_index_snapshot(symbol, candle_ist, price):
    """Archive a real completed candle, never a placeholder or synthetic quote."""
    if symbol not in INDEX_NAMES or not candle_ist or price is None:
        return False
    stamp = datetime.strptime(candle_ist, "%Y-%m-%d %H:%M:%S").replace(
        tzinfo=ZoneInfo("Asia/Kolkata"))
    url = os.environ.get("DATABASE_URL")
    if not url:
        return False
    import psycopg
    with psycopg.connect(url, connect_timeout=3) as con:
        con.execute("""
            CREATE TABLE IF NOT EXISTS index_candle_snapshots (
                symbol TEXT PRIMARY KEY,
                candle_ist TIMESTAMPTZ NOT NULL,
                price DOUBLE PRECISION NOT NULL
            )
        """)
        con.execute("""
            INSERT INTO index_candle_snapshots(symbol, candle_ist, price)
            VALUES (%s, %s, %s)
            ON CONFLICT (symbol) DO UPDATE SET
                candle_ist = EXCLUDED.candle_ist,
                price = EXCLUDED.price
            WHERE index_candle_snapshots.candle_ist < EXCLUDED.candle_ist
        """, (symbol, stamp, float(price)))
    return True


def read_index_snapshots():
    """Read archived candles. Caller must independently validate freshness."""
    url = os.environ.get("DATABASE_URL")
    if not url:
        return {}
    import psycopg
    with psycopg.connect(url, connect_timeout=3) as con:
        with con.cursor() as cur:
            cur.execute("SELECT to_regclass('public.index_candle_snapshots')")
            if cur.fetchone()[0] is None:
                return {}
            cur.execute("""
                SELECT symbol, candle_ist, price
                FROM index_candle_snapshots
                WHERE symbol IN ('NIFTY 50', 'SENSEX')
            """)
            return {
                symbol: {
                    "symbol": symbol,
                    "updated_at": stamp.astimezone(
                        ZoneInfo("Asia/Kolkata")).strftime("%Y-%m-%d %H:%M:%S"),
                    "price": price,
                }
                for symbol, stamp, price in cur.fetchall()
            }
