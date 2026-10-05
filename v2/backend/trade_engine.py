import sqlite3
from datetime import datetime
from .database import DB_PATH, init_db

def now():
    return datetime.now().astimezone().isoformat(timespec="seconds")

def connect():
    init_db()
    return sqlite3.connect(DB_PATH)

def buy(symbol, price, t1, t2, invalidation, reason):
    con = connect()
    existing = con.execute(
        "SELECT id FROM trades WHERE symbol=? AND status NOT IN ('SELL','CLOSED')",
        (symbol,)
    ).fetchone()

    if existing:
        con.close()
        return existing[0]

    cur = con.execute("""
        INSERT INTO trades
        (symbol,signal_time,entry_price,current_price,target_1,target_2,
         invalidation,status,signal_reason)
        VALUES (?,?,?,?,?,?,?,?,?)
    """, (symbol, now(), price, price, t1, t2,
          invalidation, "BUY", reason))

    trade_id = cur.lastrowid
    con.execute("""
        INSERT INTO trade_events
        (trade_id,event_time,action,price,reason)
        VALUES (?,?,?,?,?)
    """, (trade_id, now(), "BUY", price, reason))

    con.commit()
    con.close()
    return trade_id

def update_state(trade_id, price, action="HOLD", reason="Chart remains valid"):
    con = connect()
    con.execute(
        "UPDATE trades SET current_price=?, status=? WHERE id=?",
        (price, action, trade_id)
    )
    con.execute("""
        INSERT INTO trade_events
        (trade_id,event_time,action,price,reason)
        VALUES (?,?,?,?,?)
    """, (trade_id, now(), action, price, reason))
    con.commit()
    con.close()

def sell(trade_id, price, reason):
    con = connect()
    row = con.execute(
        "SELECT entry_price FROM trades WHERE id=?", (trade_id,)
    ).fetchone()

    if not row:
        con.close()
        return

    entry = row[0]
    pnl = price - entry
    pnl_pct = (pnl / entry) * 100

    con.execute("""
        UPDATE trades
        SET current_price=?, status='CLOSED',
            exit_reason=?, exit_time=?, exit_price=?,
            realized_pnl=?, realized_pnl_pct=?
        WHERE id=?
    """, (price, reason, now(), price, pnl, pnl_pct, trade_id))

    con.execute("""
        INSERT INTO trade_events
        (trade_id,event_time,action,price,reason)
        VALUES (?,?,?,?,?)
    """, (trade_id, now(), "SELL", price, reason))

    con.commit()
    con.close()

if __name__ == "__main__":
    init_db()
    print("V2_ENGINE_OK")
