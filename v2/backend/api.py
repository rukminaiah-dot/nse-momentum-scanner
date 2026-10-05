import sqlite3
from fastapi import FastAPI
from .database import DB_PATH

app = FastAPI(title="NSE Momentum Scanner V2")

@app.get("/api/v2/trades")
def get_trades():
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    rows = con.execute(
        "SELECT * FROM trades ORDER BY id DESC LIMIT 100"
    ).fetchall()
    con.close()
    return [dict(row) for row in rows]

from fastapi.responses import FileResponse

@app.get("/")
def dashboard():
    return FileResponse("v2/frontend/index.html")
