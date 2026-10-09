import sqlite3
from fastapi import FastAPI
from .database import DB_PATH
from .stock_universe import NIFTY_200

instrument_symbols = {key: symbol for symbol, key in NIFTY_200.items()}

app = FastAPI(title="NSE Momentum Scanner V2")

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
