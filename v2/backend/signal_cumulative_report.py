"""Read-only cumulative signal performance from persistent archive rows.

Long-only BUY -> SELL cycles, grouped by instrument, including overnight holds.
All figures are indicative signal-price returns, not actual execution P&L.
"""
from datetime import date, datetime, timedelta
from .signal_accuracy_report import report_from_rows
from .paper_signal_ledger import PaperLedger, Signal

def cumulative_report(rows, *, index_symbols=()):
    ledger = PaperLedger()
    seen = set()
    readings = {"BUY": 0, "SELL": 0}
    normalized = []
    for symbol, stamp, price, side in rows:
        if side not in readings:
            continue
        if isinstance(stamp, str):
            stamp = datetime.fromisoformat(stamp)
        if not isinstance(stamp, datetime) or stamp.tzinfo is not None:
            raise ValueError("timestamps must be naive IST datetimes")
        key = (symbol, stamp)
        if key in seen:
            continue
        seen.add(key)
        readings[side] += 1
        normalized.append((symbol, stamp, price, side))
    for symbol, stamp, price, side in sorted(normalized, key=lambda r: (r[1], r[0])):
        ledger.record(Signal(symbol, "index" if symbol in index_symbols else "stock",
                             side, price, stamp))
    by_day = {}
    for trade in ledger.closed:
        day = trade.sold_at.date().isoformat()
        item = by_day.setdefault(day, {"stock_closed": 0, "index_closed": 0,
                                        "stock_wins": 0, "index_wins": 0,
                                        "stock_points": 0.0, "index_points": 0.0})
        kind = trade.kind
        item[kind + "_closed"] += 1
        item[kind + "_wins"] += int(trade.points > 0)
        item[kind + "_points"] += trade.points
    return {
        "mode": "PAPER_SIGNALS_ONLY",
        "buy_readings": readings["BUY"], "sell_readings": readings["SELL"],
        "gross_closed_calls": len(ledger.closed),
        "stock": ledger.summary("stock"),
        "index": ledger.summary("index"),
        "closed_calls": [{
            "symbol": c.instrument, "kind": c.kind,
            "buy_time_ist": c.bought_at.isoformat(sep=" "),
            "sell_time_ist": c.sold_at.isoformat(sep=" "),
            "buy_price": c.buy_price, "sell_price": c.sell_price,
            "difference": c.points, "return_pct": c.return_pct
        } for c in ledger.closed],
        "daily_by_sell_date": dict(sorted(by_day.items())),
        "open_positions": [{
            "symbol": s.instrument, "kind": s.kind,
            "buy_time_ist": s.timestamp.isoformat(sep=" "), "buy_price": s.price
        } for s in ledger.open.values()],
        "rejected_readings": len(ledger.rejected),
        "pnl_inr": None,
        "note": "No combined rupee P&L: quantity, execution prices, costs and index trade instrument are unknown. Points must not be added across instruments."
    }

def fetch_cumulative_archive(connection, *, start_date, end_date):
    """Include earlier entries so exits in range can match prior BUYs.

    Returns observations through end_date, starting at archive inception.
    Filter the resulting closed_calls by sell date for period-specific metrics.
    """
    start = date.fromisoformat(start_date)
    end = date.fromisoformat(end_date)
    if end < start:
        raise ValueError("end_date must be >= start_date")
    end_exclusive = datetime.combine(end + timedelta(days=1), datetime.min.time())
    return connection.execute(
        """SELECT symbol,candle_time_ist,price,signal
           FROM scanner_signal_archive
           WHERE candle_time_ist < %s
             AND signal IN ('BUY','SELL')
           ORDER BY candle_time_ist,symbol""",
        (end_exclusive,)).fetchall()
