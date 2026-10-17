import math
import sqlite3
from datetime import datetime
from zoneinfo import ZoneInfo

from .database import DB_PATH, init_db


TERMINAL_STATUSES = {"SELL", "CLOSED"}


def now():
    return datetime.now(ZoneInfo("Asia/Kolkata")).isoformat(timespec="seconds")


def connect():
    con = sqlite3.connect(DB_PATH, timeout=10)
    con.execute("PRAGMA busy_timeout=10000")
    return con


def _positive_price(value, name):
    if isinstance(value, bool):
        raise ValueError(f"{name} must be a finite positive number")
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError(f"{name} must be a finite positive number") from exc
    if not math.isfinite(number) or number <= 0:
        raise ValueError(f"{name} must be a finite positive number")
    return number


def _backup_active_trade(trade_id):
    try:
        from .postgres_history import backup_active_trade
        backup_active_trade(trade_id)
    except Exception as exc:
        print(f"Active trade backup failed: {exc}")


def _sync_completed_history():
    try:
        from .postgres_history import save_completed_trades
        save_completed_trades()
    except Exception as exc:
        print(f"PostgreSQL trade history sync failed: {exc}")


def buy(symbol, price, t1, t2, invalidation, reason):
    price = _positive_price(price, "entry price")
    t1 = _positive_price(t1, "target 1")
    t2 = _positive_price(t2, "target 2")
    invalidation = _positive_price(invalidation, "invalidation")
    if not isinstance(symbol, str) or not symbol.strip():
        raise ValueError("symbol must be a non-empty string")

    con = connect()
    try:
        # Lock before checking for an existing active record so concurrent
        # callbacks cannot create duplicate BUY lifecycles for one symbol.
        con.execute("BEGIN IMMEDIATE")
        existing = con.execute(
            "SELECT id FROM trades WHERE symbol=? AND status NOT IN ('SELL','CLOSED') ORDER BY id DESC LIMIT 1",
            (symbol,),
        ).fetchone()
        if existing:
            con.commit()
            return existing[0]

        signal_time = now()
        cur = con.execute("""
            INSERT INTO trades
            (symbol,signal_time,entry_price,current_price,target_1,target_2,
             invalidation,status,signal_reason)
            VALUES (?,?,?,?,?,?,?,?,?)
        """, (symbol, signal_time, price, price, t1, t2,
              invalidation, "BUY", reason))
        trade_id = cur.lastrowid
        con.execute("""
            INSERT INTO trade_events
            (trade_id,event_time,action,price,reason)
            VALUES (?,?,?,?,?)
        """, (trade_id, signal_time, "BUY", price, reason))
        con.commit()
    except Exception:
        con.rollback()
        raise
    finally:
        con.close()

    _backup_active_trade(trade_id)
    return trade_id


def update_state(trade_id, price, action="HOLD", reason="Chart remains valid"):
    price = _positive_price(price, "current price")
    if action in TERMINAL_STATUSES:
        raise ValueError("terminal trade states must be recorded with sell()")

    con = connect()
    try:
        con.execute("BEGIN IMMEDIATE")
        row = con.execute(
            "SELECT status FROM trades WHERE id=?", (trade_id,)
        ).fetchone()
        if not row or row[0] in TERMINAL_STATUSES:
            con.commit()
            return False

        old_status = row[0]
        con.execute(
            "UPDATE trades SET current_price=?, status=? WHERE id=?",
            (price, action, trade_id),
        )
        if old_status != action:
            con.execute("""
                INSERT INTO trade_events
                (trade_id,event_time,action,price,reason)
                VALUES (?,?,?,?,?)
            """, (trade_id, now(), action, price, reason))
        con.commit()
        return True
    except Exception:
        con.rollback()
        raise
    finally:
        con.close()


def sell(trade_id, price, reason):
    price = _positive_price(price, "exit price")
    con = connect()
    try:
        con.execute("BEGIN IMMEDIATE")
        row = con.execute(
            "SELECT entry_price, status FROM trades WHERE id=?", (trade_id,)
        ).fetchone()
        if not row or row[1] in TERMINAL_STATUSES:
            con.commit()
            return False

        entry = _positive_price(row[0], "stored entry price")
        pnl = price - entry
        pnl_pct = (pnl / entry) * 100
        exit_time = now()
        con.execute("""
            UPDATE trades
            SET current_price=?, status='CLOSED',
                exit_reason=?, exit_time=?, exit_price=?,
                realized_pnl=?, realized_pnl_pct=?
            WHERE id=?
        """, (price, reason, exit_time, price, pnl, pnl_pct, trade_id))
        con.execute("""
            INSERT INTO trade_events
            (trade_id,event_time,action,price,reason)
            VALUES (?,?,?,?,?)
        """, (trade_id, exit_time, "SELL", price, reason))
        con.commit()
    except Exception:
        con.rollback()
        raise
    finally:
        con.close()

    _backup_active_trade(trade_id)
    _sync_completed_history()
    return True


if __name__ == "__main__":
    init_db()
    print("V2_ENGINE_OK")
