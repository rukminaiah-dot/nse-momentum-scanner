import os
import psycopg

def init_history():
    url = os.environ.get("DATABASE_URL")
    if not url:
        print("DATABASE_URL not set; PostgreSQL history skipped")
        return

    with psycopg.connect(url) as con:
        con.execute("""
            CREATE TABLE IF NOT EXISTS daily_trade_history (
                id BIGSERIAL PRIMARY KEY,
                trade_date DATE NOT NULL,
                source_trade_id INTEGER,
                symbol TEXT NOT NULL,
                buy_time TIMESTAMPTZ,
                buy_price NUMERIC,
                sell_time TIMESTAMPTZ,
                sell_price NUMERIC,
                quantity INTEGER DEFAULT 1,
                pnl_per_share NUMERIC,
                pnl_total NUMERIC,
                pnl_pct NUMERIC,
                status TEXT,
                buy_reason TEXT,
                exit_reason TEXT,
                UNIQUE (trade_date, source_trade_id)
            )
        """)
    print("PostgreSQL history table ready")

if __name__ == "__main__":
    init_history()

def save_completed_trades():
    """Copy completed SQLite trades into persistent PostgreSQL history."""
    import sqlite3
    from datetime import datetime
    from zoneinfo import ZoneInfo
    from .database import DB_PATH

    url = os.environ.get("DATABASE_URL")
    if not url:
        print("PostgreSQL history sync skipped: DATABASE_URL missing")
        return 0

    with sqlite3.connect(DB_PATH) as sqlite_con:
        rows = sqlite_con.execute("""
            SELECT id, symbol, signal_time, entry_price,
                   exit_time, exit_price, realized_pnl,
                   realized_pnl_pct, status, signal_reason, exit_reason
            FROM trades
            WHERE status IN ('CLOSED', 'SELL')
              AND exit_time IS NOT NULL
        """).fetchall()

    ist = ZoneInfo("Asia/Kolkata")

    def parse_time(value):
        if not value:
            return None
        dt = datetime.fromisoformat(value)
        return dt.replace(tzinfo=ist) if dt.tzinfo is None else dt

    saved = 0

    with psycopg.connect(url) as pg:

        for row in rows:
            (trade_id, symbol, buy_time, buy_price,
             sell_time, sell_price, pnl, pnl_pct,
             status, buy_reason, exit_reason) = row

            buy_dt = parse_time(buy_time)
            sell_dt = parse_time(sell_time)

            result = pg.execute("""
                INSERT INTO daily_trade_history (
                    trade_date, source_trade_id, symbol,
                    buy_time, buy_price, sell_time, sell_price,
                    quantity, pnl_per_share, pnl_total, pnl_pct,
                    status, buy_reason, exit_reason
                )
                VALUES (
                    %s, %s, %s, %s, %s, %s, %s,
                    1, %s, %s, %s, %s, %s, %s
                )
                ON CONFLICT (trade_date, source_trade_id)
                DO NOTHING
                RETURNING id
            """, (
                buy_dt.date(), trade_id, symbol,
                buy_dt, buy_price, sell_dt, sell_price,
                pnl, pnl, pnl_pct, status, buy_reason, exit_reason
            ))

            if result.fetchone():
                saved += 1

    print(f"PostgreSQL completed trades saved: {saved}")
    return saved
