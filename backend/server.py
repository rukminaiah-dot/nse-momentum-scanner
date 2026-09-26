from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import backend.scanner as scanner

app = FastAPI(title="NSE/BSE Momentum Scanner API")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=False, allow_methods=["*"], allow_headers=["*"])

class ScripRequest(BaseModel):
    ticker: str

def normalize_ticker(value: str) -> str:
    ticker = value.strip().upper()
    if not ticker:
        raise HTTPException(status_code=400, detail="Ticker is required")
    if "." not in ticker:
        ticker += ".NS"
    return ticker

def clear_scan_cache():
    scanner._CACHE["at"] = 0.0
    scanner._CACHE["data"] = []

@app.get("/")
def home():
    return {"status": "ok", "app": "NSE/BSE Momentum Scanner", "mode": "paper"}

@app.get("/health")
def health():
    return {"status": "healthy"}

@app.get("/universe")
def get_universe():
    return {"count": len(scanner.SYMBOLS), "symbols": scanner.SYMBOLS}

@app.post("/universe")
def add_scrip(request: ScripRequest):
    ticker = normalize_ticker(request.ticker)
    if ticker in scanner.SYMBOLS:
        return {"status": "exists", "ticker": ticker, "count": len(scanner.SYMBOLS)}
    scanner.SYMBOLS.append(ticker)
    clear_scan_cache()
    return {"status": "added", "ticker": ticker, "count": len(scanner.SYMBOLS),
            "note": "Runtime change; resets when the Render service restarts."}

@app.delete("/universe/{ticker}")
def remove_scrip(ticker: str):
    ticker = normalize_ticker(ticker)
    if ticker not in scanner.SYMBOLS:
        raise HTTPException(status_code=404, detail=f"{ticker} is not in the universe")
    scanner.SYMBOLS.remove(ticker)
    clear_scan_cache()
    return {"status": "removed", "ticker": ticker, "count": len(scanner.SYMBOLS),
            "note": "Runtime change; resets when the Render service restarts."}

@app.get("/signals")
def get_signals():
    result = scanner.signals()
    return {"mode": "scanner", "universe_count": len(scanner.SYMBOLS), "count": len(result),
            "signals": result, "message": "Observed momentum scan; not a prediction or recommendation."}
