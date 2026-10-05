import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "v2_trades.db"

def init_db():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(DB_PATH)
    con.execute("""
        CREATE TABLE IF NOT EXISTS trades (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol TEXT NOT NULL,
            signal_time TEXT NOT NULL,
            entry_price REAL NOT NULL,
            current_price REAL,
            target_1 REAL,
            target_2 REAL,
            invalidation REAL,
            status TEXT NOT NULL DEFAULT 'BUY',
            signal_reason TEXT,
            exit_reason TEXT,
            exit_time TEXT,
            exit_price REAL,
            realized_pnl REAL,
            realized_pnl_pct REAL
        )
    """)
    con.execute("""
        CREATE TABLE IF NOT EXISTS trade_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            trade_id INTEGER NOT NULL,
            event_time TEXT NOT NULL,
            action TEXT NOT NULL,
            price REAL,
            reason TEXT,
            FOREIGN KEY(trade_id) REFERENCES trades(id)
        )
    """)
    con.commit()
    con.close()

if __name__ == "__main__":
    init_db()
    print("V2_DB_OK")
