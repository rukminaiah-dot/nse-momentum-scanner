from .expiry_signals import expiry_signal, candle_is_fresh
from .smart_option_api import router as smart_option_router
from .expiry_momentum import expiry_watch_status
import sqlite3
from fastapi import FastAPI
from .database import DB_PATH
from .stock_universe import NIFTY_200

instrument_symbols = {key: symbol for symbol, key in NIFTY_200.items()}

app = FastAPI(title="NSE Momentum Scanner V2")
app.include_router(smart_option_router)

@app.get("/api/v2/trades")
def get_trades():
    con = sqlite3.connect(DB_PATH, timeout=10)
    con.row_factory = sqlite3.Row
    rows = con.execute(
        "SELECT * FROM trades ORDER BY id DESC LIMIT 100"
    ).fetchall()
    con.close()
    items = [dict(row) for row in rows]
    for item in items:
        item["symbol"] = instrument_symbols.get(item["symbol"], item["symbol"])
    return items

from fastapi.responses import FileResponse

@app.get("/")
def dashboard():
    return FileResponse("v2/frontend/index.html")

@app.get("/api/v2/scanner")
def get_scanner_results():
    con = sqlite3.connect(DB_PATH, timeout=10)
    con.row_factory = sqlite3.Row
    rows = con.execute(
        "SELECT * FROM scanner_results ORDER BY updated_at DESC"
    ).fetchall()
    con.close()
    return [dict(row) for row in rows]


@app.get("/api/v2/history")
def get_daily_trade_history():
    import os
    import psycopg
    from psycopg.rows import dict_row
    from fastapi import HTTPException

    url = os.environ.get("DATABASE_URL")
    if not url:
        raise HTTPException(
            status_code=503,
            detail="PostgreSQL history database not configured"
        )

    try:
        with psycopg.connect(url, row_factory=dict_row) as con:
            rows = con.execute("""
                SELECT
                    id, trade_date, source_trade_id, symbol,
                    buy_time, buy_price, sell_time, sell_price,
                    quantity, pnl_per_share, pnl_total, pnl_pct,
                    status, buy_reason, exit_reason
                FROM daily_trade_history
                ORDER BY trade_date DESC, sell_time DESC
                LIMIT 500
            """).fetchall()

        for item in rows:
            item["symbol"] = instrument_symbols.get(
                item["symbol"], item["symbol"]
            )

        return rows

    except psycopg.Error as exc:
        print(f"PostgreSQL history API error: {exc}")
        raise HTTPException(
            status_code=503,
            detail="Trade history temporarily unavailable"
        ) from exc

@app.get("/history")
def history_page():
    return FileResponse("v2/frontend/history.html")

@app.get("/smart-option-buyer")
def smart_option_buyer_page():
    return FileResponse("v2/frontend/smart-option-buyer.html")


@app.get("/expiry-momentum")
def expiry_momentum_page():
    return FileResponse("v2/frontend/expiry-momentum.html")


@app.get("/api/v2/expiry-signals")
def get_expiry_signals():
    """Research-only expiry signals. No automatic orders."""
    rows = get_scanner_results()
    output = []
    for name in ("NIFTY 50", "SENSEX"):
        row = next((r for r in rows if r["symbol"] == name), None)
        from datetime import datetime
        from zoneinfo import ZoneInfo

        now = datetime.now(ZoneInfo("Asia/Kolkata"))
        status = expiry_watch_status(name, now)

        if status != "WATCH":
            reason = status
        elif row is None:
            reason = "DATA_UNAVAILABLE"
        elif not candle_is_fresh(row.get("updated_at"), now):
            reason = "STALE_DATA"
        else:
            reason = "SAFETY_CHECKS_PASSED"

        output.append({
            "index": name,
            "signal": "NO TRADE",
            "reason": reason,
            "price": row.get("price") if row else None,
            "updated_at": row.get("updated_at") if row else None,
        })
    return output


@app.get("/api/v2/nifty200-feed-health")
def nifty200_feed_health():
    """Read-only feed coverage, based on actual scanner-process ticks."""
    import json
    import time
    from pathlib import Path
    from datetime import datetime
    from zoneinfo import ZoneInfo
    now = time.time()
    ist = datetime.now(ZoneInfo("Asia/Kolkata"))
    base = {
        "universe_size": len(NIFTY_200),
        "checked_at_ist": ist.isoformat(),
        "market_session": "OPEN" if ist.weekday() < 5 and (9, 15) <= (ist.hour, ist.minute) <= (15, 30) else "CLOSED",
        "recent_tick_window_seconds": 120,
        "order_execution_enabled": False,
    }
    try:
        data = json.loads(Path("/tmp/nse_200_feed_health.json").read_text())
        observed = float(data["observed_at_epoch"])
        seen = data["last_tick_epoch"]
        if not isinstance(seen, dict) or observed > now + 30:
            raise ValueError("Invalid feed-health snapshot")
        valid_keys = set(NIFTY_200.values())
        observed_keys = valid_keys.intersection(seen)
        recent = sum(1 for k in observed_keys
                     if isinstance(seen[k], (int, float))
                     and 0 <= now - seen[k] <= 120)
        base.update(
            status="REPORTING" if now - observed <= 30 else "STALE_REPORT",
            snapshot_age_seconds=round(max(0, now - observed), 1),
            stocks_ever_observed=len(observed_keys),
            stocks_with_recent_ticks=recent,
            stocks_without_recent_ticks=len(valid_keys) - recent,
        )
    except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError):
        base.update(status="NO_FEED_REPORT", stocks_ever_observed=0,
                    stocks_with_recent_ticks=0, stocks_without_recent_ticks=len(NIFTY_200))
    try:
        connection = json.loads(Path("/tmp/nse_200_connection_health.json").read_text())
        base["connection_last_event"] = connection.get("status", "UNKNOWN")
        base["connection_event_at_ist"] = connection.get("event_at_ist")
        base["connection_state_note"] = "Last recorded event; not a continuous connection guarantee"
    except (OSError, ValueError, TypeError):
        base["connection_last_event"] = "UNKNOWN"
        base["connection_state_note"] = "No connection event recorded"
    if base["market_session"] == "CLOSED" and base["status"] == "STALE_REPORT":
        base["status"] = "MARKET_CLOSED_TICK_REPORT_STALE"
    return base


@app.get("/api/v2/top-momentum-setups")
def top_momentum_setups():
    """Rank verified fresh scanner candidates; research only, never place orders."""
    from datetime import datetime, time as clock_time, timedelta
    from math import isfinite
    from zoneinfo import ZoneInfo
    now = datetime.now(ZoneInfo("Asia/Kolkata"))
    session_open = now.weekday() < 5 and clock_time(9, 15) <= now.time() < clock_time(15, 30)
    output = {"status": "MARKET_CLOSED" if not session_open else "NO_QUALIFYING_SETUPS",
              "as_of_ist": now.isoformat(), "universe_size": len(NIFTY_200),
              "order_execution_enabled": False, "mode": "MANUAL_RESEARCH_ONLY",
              "setups": [], "fresh_stock_rows": 0, "rejected_stale_rows": 0}
    if not session_open:
        return output
    try:
        with sqlite3.connect(DB_PATH, timeout=5) as db:
            db.row_factory = sqlite3.Row
            rows = [dict(row) for row in db.execute(
                "SELECT symbol,updated_at,price,ema9,ema20,momentum,market,trend_5m,signal FROM scanner_results")]
    except sqlite3.Error:
        output["status"] = "SCANNER_DATABASE_UNAVAILABLE"
        return output
    eligible_symbols = set(NIFTY_200)
    for row in rows:
        if row["symbol"] not in eligible_symbols:
            continue
        try:
            stamp = datetime.strptime(row["updated_at"], "%Y-%m-%d %H:%M:%S").replace(tzinfo=ZoneInfo("Asia/Kolkata"))
            if stamp.date() != now.date() or not timedelta(0) <= now - stamp <= timedelta(minutes=3):
                output["rejected_stale_rows"] += 1
                continue
            output["fresh_stock_rows"] += 1
            price, e9, e20, mom = (float(row[k]) for k in ("price", "ema9", "ema20", "momentum"))
            if not all(isfinite(v) for v in (price, e9, e20, mom)) or min(price, e9, e20) <= 0:
                continue
            if row["signal"] != "BUY" or row["trend_5m"] != "BULLISH" or not (price > e9 > e20 and mom > 0):
                continue
            # These are scanner-derived indicative levels, NOT ATR-validated executable orders.
            # Without an independently verified ATR, suppress targets and stops.
            score = round(mom + 100 * (e9 - e20) / price, 4)
            output["setups"].append({
                "symbol": row["symbol"], "last_price": round(price, 2),
                "indicative_entry": round(price, 2),
                "target_1": None, "target_2": None, "stop_loss": None,
                "levels_status": "ATR_LEVELS_NOT_VERIFIED",
                "momentum_pct": round(mom, 3), "ema9": round(e9, 2),
                "ema20": round(e20, 2), "trend_5m": row["trend_5m"],
                "candle_ist": row["updated_at"], "rank_score": score,
                "reasons": ["FRESH_COMPLETED_CANDLE", "BUY_SIGNAL",
                            "BULLISH_5M_TREND", "EMA9_ABOVE_EMA20", "POSITIVE_MOMENTUM"],
                "trade_status": "RESEARCH_ONLY",
            })
        except (ValueError, TypeError, OverflowError):
            continue
    output["setups"].sort(key=lambda item: (-item["rank_score"], item["symbol"]))
    output["setups"] = output["setups"][:5]
    if output["setups"]:
        output["status"] = "RESEARCH_SHORTLIST"
    return output
