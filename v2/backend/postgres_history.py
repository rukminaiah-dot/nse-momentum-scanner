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

def init_active_trade_backup():
    """Create persistent storage for active trades."""
    url = os.environ.get("DATABASE_URL")
    if not url:
        print("Active trade backup skipped: DATABASE_URL missing")
        return

    with psycopg.connect(url) as con:
        con.execute("""
            CREATE TABLE IF NOT EXISTS active_trade_backup (
                trade_uuid TEXT PRIMARY KEY,
                symbol TEXT NOT NULL,
                signal_time TIMESTAMPTZ NOT NULL,
                entry_price DOUBLE PRECISION NOT NULL,
                current_price DOUBLE PRECISION,
                target_1 DOUBLE PRECISION,
                target_2 DOUBLE PRECISION,
                invalidation DOUBLE PRECISION,
                status TEXT NOT NULL,
                signal_reason TEXT,
                updated_at TIMESTAMPTZ DEFAULT NOW()
            )
        """)
    print("PostgreSQL active trade backup table ready")

if __name__ == "__main__":
    init_active_trade_backup()

def backup_active_trade(trade_id):
    """Save an active SQLite trade to PostgreSQL."""
    import sqlite3
    from datetime import datetime
    from zoneinfo import ZoneInfo
    from .database import DB_PATH

    url = os.environ.get("DATABASE_URL")
    if not url:
        return

    with sqlite3.connect(DB_PATH) as db:
        db.row_factory = sqlite3.Row
        row = db.execute(
            "SELECT * FROM trades WHERE id=?",
            (trade_id,)
        ).fetchone()

    if not row:
        return

    trade = dict(row)
    buy_time = datetime.fromisoformat(trade["signal_time"])
    if buy_time.tzinfo is None:
        buy_time = buy_time.replace(tzinfo=ZoneInfo("Asia/Kolkata"))

    trade_uuid = f"{buy_time.date()}:{trade['symbol']}:{buy_time.isoformat()}"

    with psycopg.connect(url) as pg:
        pg.execute("""
            INSERT INTO active_trade_backup (
                trade_uuid, symbol, signal_time, entry_price,
                current_price, target_1, target_2, invalidation,
                status, signal_reason, updated_at
            )
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,NOW())
            ON CONFLICT (trade_uuid) DO UPDATE SET
                current_price=EXCLUDED.current_price,
                status=EXCLUDED.status,
                updated_at=NOW()
        """, (
            trade_uuid, trade["symbol"], buy_time,
            trade["entry_price"], trade["current_price"],
            trade["target_1"], trade["target_2"],
            trade["invalidation"], trade["status"],
            trade["signal_reason"]
        ))

def restore_active_trades():
    """Restore today's active trades from PostgreSQL into SQLite."""
    import sqlite3
    from datetime import datetime
    from zoneinfo import ZoneInfo
    from .database import DB_PATH

    url = os.environ.get("DATABASE_URL")
    if not url:
        return 0

    today = datetime.now(ZoneInfo("Asia/Kolkata")).date()

    with psycopg.connect(url) as pg:
        rows = pg.execute("""
            SELECT symbol, signal_time, entry_price, current_price,
                   target_1, target_2, invalidation, status, signal_reason
            FROM active_trade_backup
            WHERE (signal_time AT TIME ZONE 'Asia/Kolkata')::date = %s
              AND status IN ('BUY', 'TARGET_1', 'HOLD')
        """, (today,)).fetchall()

    restored = 0

    with sqlite3.connect(DB_PATH, timeout=10) as db:
        for row in rows:
            symbol, signal_time, entry, current, t1, t2, stop, status, reason = row

            existing = db.execute("""
                SELECT id FROM trades
                WHERE symbol=? AND status NOT IN ('CLOSED','SELL')
            """, (symbol,)).fetchone()

            if existing:
                continue

            closed_today = db.execute("""
                SELECT id FROM trades
                WHERE symbol=?
                  AND substr(signal_time, 1, 10)=?
                  AND status IN ('CLOSED', 'SELL')
                LIMIT 1
            """, (symbol, str(today))).fetchone()

            if closed_today:
                continue

            db.execute("""
                INSERT INTO trades (
                    symbol, signal_time, entry_price, current_price,
                    target_1, target_2, invalidation, status, signal_reason
                ) VALUES (?,?,?,?,?,?,?,?,?)
            """, (
                symbol, signal_time.isoformat(), entry, current,
                t1, t2, stop, status, reason
            ))
            restored += 1

        db.commit()

    print(f"ACTIVE TRADES RESTORED: {restored}")
    return restored
