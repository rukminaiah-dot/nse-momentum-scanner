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
