import sqlite3
from pathlib import Path
from .stock_universe import NIFTY_200

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "v2_trades.db"

def init_db():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(DB_PATH, timeout=10)
    con.execute("PRAGMA journal_mode=WAL")
    con.execute("PRAGMA busy_timeout=10000")
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
    con.execute("""CREATE TABLE IF NOT EXISTS scanner_results (symbol TEXT PRIMARY KEY, updated_at TEXT NOT NULL, price REAL, ema9 REAL, ema20 REAL, momentum REAL, market TEXT, trend_5m TEXT, signal TEXT)""")
    con.executemany("""INSERT OR IGNORE INTO scanner_results (symbol,updated_at,signal) VALUES (?,datetime('now','+5 hours','+30 minutes'),'WAITING')""", [(symbol,) for symbol in NIFTY_200.keys()])
    columns = [row[1] for row in con.execute("PRAGMA table_info(scanner_results)")]
    if "previous_close" not in columns:
        con.execute("ALTER TABLE scanner_results ADD COLUMN previous_close REAL")
    con.commit()
    con.close()

if __name__ == "__main__":
    init_db()
    print("V2_DB_OK")


def reset_scanner_results():
    con = sqlite3.connect(DB_PATH, timeout=10)
    con.execute("PRAGMA busy_timeout=10000")
    con.execute("""
        UPDATE scanner_results
        SET updated_at=datetime('now','+5 hours','+30 minutes'),
            price=NULL, ema9=NULL, ema20=NULL, momentum=NULL,
            market=NULL, trend_5m=NULL, signal='WAITING'
    """)
    con.commit()
    con.close()
