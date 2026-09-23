from fastapi import FastAPI
from backend.scanner import signals as scan_signals
app = FastAPI(title="NSE/BSE Momentum Scanner API")

@app.get("/")
def home():
    return {"status": "ok", "app": "NSE/BSE Momentum Scanner"}

@app.get("/health")
def health():
    return {"status": "healthy"}

@app.get("/signals")
def signals():
    return {
        "mode": "scanner",
        "signals": scan_signals(),
        "message": "Observed momentum scan; not a prediction."
    }

