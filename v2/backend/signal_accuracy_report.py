"""Read-only audit of actually persisted scanner signal readings.

This does not infer unrecorded calls or place orders. SQLite history is
ephemeral on some hosting plans; results are only as complete as its rows.
"""
import sqlite3
from datetime import date, datetime, timedelta
from .paper_signal_ledger import PaperLedger, Signal

def report_from_rows(rows, *, day=None, index_symbols=()):
    """Rows: (symbol, candle_time_IST, price, signal), chronological or not."""
    if day is not None:
        day = date.fromisoformat(day) if isinstance(day, str) else day
    ledger = PaperLedger()
    unique = {}
    for symbol, stamp, price, side in rows:
        if side not in ("BUY", "SELL"):
            continue
        if not isinstance(stamp, datetime):
            stamp = datetime.fromisoformat(stamp)
        if stamp.tzinfo is not None:
            raise ValueError("candle_time must be naive IST")
        if day is not None and stamp.date() != day:
            continue
        unique[(symbol, stamp)] = (symbol, stamp, price, side)
    for symbol, stamp, price, side in sorted(unique.values(), key=lambda r: (r[1], r[0])):
        ledger.record(Signal(symbol, "index" if symbol in index_symbols else "stock",
                             side, price, stamp))
    closed = [{"instrument": c.instrument, "type": c.kind,
               "buy_time_ist": c.bought_at.isoformat(sep=" "),
               "sell_time_ist": c.sold_at.isoformat(sep=" "),
               "buy_price": c.buy_price, "sell_price": c.sell_price,
               "price_difference": c.points, "return_pct": c.return_pct}
              for c in ledger.closed]
    return {
        "status": "RECORDED_HISTORY_ONLY" if unique else "NO_RECORDED_SIGNALS",
        "date_ist": day.isoformat() if day else None,
        "gross_buy_readings": sum(row[3] == "BUY" for row in unique.values()),
        "gross_sell_readings": sum(row[3] == "SELL" for row in unique.values()),
        "closed_calls": closed,
        "stock": ledger.summary("stock"),
        "index": ledger.summary("index"),
        "open_positions": [{"instrument": s.instrument, "type": s.kind,
                            "buy_price": s.price, "buy_time_ist": s.timestamp.isoformat(sep=" ")}
                           for s in ledger.open.values()],
        "rejected_readings": len(ledger.rejected),
        "note": "Signal-price paper results, not executions. Stock price changes and index points cannot be summed into rupee P&L. Missing history may undercount calls. No fees, slippage or position sizing."
    }

def report_from_sqlite(db_path, day, *, index_symbols=()):
    date.fromisoformat(day)
    next_day = (date.fromisoformat(day) + timedelta(days=1)).isoformat()
    with sqlite3.connect(db_path, timeout=5) as db:
        rows = db.execute(
            """SELECT symbol,candle_time,price,signal FROM scanner_signal_history
               WHERE candle_time >= ? AND candle_time < ?
                 AND signal IN ('BUY','SELL')
               ORDER BY candle_time,symbol""",
            (day + " 00:00:00", next_day + " 00:00:00")).fetchall()
    return report_from_rows(rows, day=day, index_symbols=index_symbols)
