import os
import psycopg
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import backend.scanner as scanner

app = FastAPI(title="NSE/BSE Momentum Scanner API")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=False, allow_methods=["*"], allow_headers=["*"])
DATABASE_URL = os.environ.get("DATABASE_URL")

class ScripRequest(BaseModel):
    ticker: str

def normalize_ticker(value):
    ticker = value.strip().upper()
    if not ticker:
        raise HTTPException(400, "Ticker is required")
    if "." not in ticker:
        ticker += ".NS"
    if not ticker.endswith((".NS", ".BO")):
        raise HTTPException(400, "Use an NSE (.NS) or BSE (.BO) ticker")
    return ticker

def connect():
    if not DATABASE_URL:
        raise HTTPException(503, "DATABASE_URL is not configured")
    return psycopg.connect(DATABASE_URL)

def init_db():
    if DATABASE_URL:
        with psycopg.connect(DATABASE_URL) as conn:
            conn.execute("""CREATE TABLE IF NOT EXISTS universe_changes (
                ticker TEXT PRIMARY KEY, enabled BOOLEAN NOT NULL,
                updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW())""")
            conn.execute("""CREATE TABLE IF NOT EXISTS signal_history (
                id BIGSERIAL PRIMARY KEY,
                ticker TEXT NOT NULL,
                entry DOUBLE PRECISION NOT NULL,
                target_1 DOUBLE PRECISION NOT NULL,
                target_2 DOUBLE PRECISION NOT NULL,
                invalidation DOUBLE PRECISION NOT NULL,
                status TEXT NOT NULL DEFAULT 'ACTIVE',
                triggered_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )""")

def current_symbols():
    symbols = set(scanner.SYMBOLS)
    if DATABASE_URL:
        with connect() as conn:
            for ticker, enabled in conn.execute("SELECT ticker, enabled FROM universe_changes"):
                symbols.add(ticker) if enabled else symbols.discard(ticker)
    return sorted(symbols)

def record_signals(signals):
    if not DATABASE_URL:
        return
    with connect() as conn:
        for x in signals:
            if not conn.execute("SELECT 1 FROM signal_history WHERE ticker=%s AND status='ACTIVE' LIMIT 1",(x["ticker"],)).fetchone():
                conn.execute("INSERT INTO signal_history (ticker,entry,target_1,target_2,invalidation) VALUES (%s,%s,%s,%s,%s)",(x["ticker"],x["entry"],x["target_1"],x["target_2"],x["invalidation"]))

def clear_cache():
    scanner._CACHE["at"] = 0.0
    scanner._CACHE["data"] = []

@app.on_event("startup")
def startup():
    init_db()

@app.get("/")
def home():
    return {"status":"ok","app":"NSE/BSE Momentum Scanner","mode":"paper"}

@app.get("/health")
def health():
    return {"status":"healthy","database":"configured" if DATABASE_URL else "missing"}

@app.get("/universe")
def universe():
    s = current_symbols()
    return {"count":len(s),"symbols":s}

@app.post("/universe")
def add_scrip(request: ScripRequest):
    ticker = normalize_ticker(request.ticker)
    with connect() as conn:
        conn.execute("""INSERT INTO universe_changes(ticker,enabled,updated_at)
        VALUES(%s,TRUE,NOW()) ON CONFLICT(ticker) DO UPDATE
        SET enabled=TRUE,updated_at=NOW()""",(ticker,))
    clear_cache()
    return {"status":"added","ticker":ticker,"count":len(current_symbols()),"persistent":True}

@app.delete("/universe/{ticker}")
def remove_scrip(ticker: str):
    ticker = normalize_ticker(ticker)
    if ticker not in current_symbols():
        raise HTTPException(404, f"{ticker} is not in the universe")
    with connect() as conn:
        conn.execute("""INSERT INTO universe_changes(ticker,enabled,updated_at)
        VALUES(%s,FALSE,NOW()) ON CONFLICT(ticker) DO UPDATE
        SET enabled=FALSE,updated_at=NOW()""",(ticker,))
    clear_cache()
    return {"status":"removed","ticker":ticker,"count":len(current_symbols()),"persistent":True}

@app.get("/signals")
def get_signals():
    original = scanner.SYMBOLS
    scanner.SYMBOLS = current_symbols()
    try:
        result = scanner.signals()
        record_signals(result)
        universe_count = len(scanner.SYMBOLS)
    finally:
        scanner.SYMBOLS = original
    return {"mode":"scanner","universe_count":universe_count,"count":len(result),
            "signals":result,"message":"Observed momentum scan; not a prediction or recommendation."}

@app.get("/diagnostics/upstox")
def upstox_diagnostics():
    import os
    return {"token_present": bool(os.getenv("UPSTOX_ACCESS_TOKEN"))}
