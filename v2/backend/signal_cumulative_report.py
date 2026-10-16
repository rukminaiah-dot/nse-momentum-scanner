"""Read-only cumulative signal performance from persistent archive rows.

Long-only BUY -> SELL cycles, grouped by instrument, including overnight holds.
All figures are indicative signal-price returns, not actual execution P&L.
"""
from datetime import date, datetime, timedelta
from math import isfinite
from .paper_signal_ledger import PaperLedger, Signal

def cumulative_report(rows, *, index_symbols=()):
    ledger = PaperLedger()
    seen = {}
    readings = {"BUY": 0, "SELL": 0}
    normalized = []
    for symbol, stamp, price, side in rows:
        if side not in readings:
            continue
        if isinstance(stamp, str):
            stamp = datetime.fromisoformat(stamp)
        if not isinstance(stamp, datetime) or stamp.tzinfo is not None:
            raise ValueError("timestamps must be naive IST datetimes")
        if not isinstance(symbol, str) or not symbol.strip():
            raise ValueError("archived instrument must be a nonempty string")
        try:
            numeric_price = float(price)
        except (TypeError, ValueError, OverflowError) as exc:
            raise ValueError("archived price must be finite and positive") from exc
        if not isfinite(numeric_price) or numeric_price <= 0:
            raise ValueError("archived price must be finite and positive")
        key = (symbol, stamp)
        if key in seen:
            if seen[key] != (numeric_price, side):
                raise ValueError("conflicting archived observations for one candle")
            continue
        seen[key] = (numeric_price, side)
        readings[side] += 1
        normalized.append((symbol, stamp, numeric_price, side))
    for symbol, stamp, price, side in sorted(normalized, key=lambda r: (r[1], r[0])):
        ledger.record(Signal(symbol, "index" if symbol in index_symbols else "stock",
                             side, price, stamp))
    by_day = {}
    for trade in ledger.closed:
        day = trade.sold_at.date().isoformat()
        item = by_day.setdefault(day, {"stock_closed": 0, "index_closed": 0,
                                        "stock_wins": 0, "index_wins": 0,
                                        "stock_losses": 0, "index_losses": 0,
                                        "stock_flat": 0, "index_flat": 0,
                                        "stock_points": 0.0, "index_points": 0.0})
        kind = trade.kind
        item[kind + "_closed"] += 1
        item[kind + "_wins"] += int(trade.points > 0)
        item[kind + "_losses"] += int(trade.points < 0)
        item[kind + "_flat"] += int(trade.points == 0)
        item[kind + "_points"] += trade.points
    return {
        "mode": "PAPER_SIGNALS_ONLY",
        "buy_readings": readings["BUY"], "sell_readings": readings["SELL"],
        "gross_closed_calls": len(ledger.closed),
        "observed_signal_readings": readings["BUY"] + readings["SELL"],
        "observation_status": "NO_ARCHIVED_BUY_SELL_READINGS" if not normalized else (
            "NO_COMPLETED_CALLS" if not ledger.closed else "COMPLETED_CALLS_OBSERVED"
        ),
        "gross_open_calls": len(ledger.open),
        "gross_distinct_calls": len(ledger.closed) + len(ledger.open),
        "call_count_rule": "One BUY opens a call per instrument; repeated BUY readings do not open more calls; first subsequent SELL closes it.",
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
        "duplicate_buy_readings": sum(reason == "duplicate BUY" for _, reason in ledger.rejected),
        "unmatched_sell_readings": sum(reason == "SELL without BUY" for _, reason in ledger.rejected),
        "pnl_inr": None,
        "note": "No combined rupee P&L: quantity, execution prices, costs and index trade instrument are unknown. Points must not be added across instruments."
    }

def fetch_cumulative_archive(connection, *, end_date):
    """Include all earlier entries so exits can match prior BUYs."""
    end = date.fromisoformat(end_date)
    end_exclusive = datetime.combine(end + timedelta(days=1), datetime.min.time())
    return connection.execute(
        """SELECT symbol,candle_time_ist,price,signal
           FROM scanner_signal_archive
           WHERE candle_time_ist < %s
             AND signal IN ('BUY','SELL')
           ORDER BY candle_time_ist,symbol""",
        (end_exclusive,)).fetchall()
