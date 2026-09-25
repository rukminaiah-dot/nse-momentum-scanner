from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from backend.scanner import signals

app = FastAPI(title="NSE/BSE Momentum Scanner API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
def home():
    return {
        "status": "ok",
        "app": "NSE/BSE Momentum Scanner",
        "mode": "paper"
    }

@app.get("/health")
def health():
    return {"status": "healthy"}

@app.get("/signals")
def get_signals():
    result = signals()

    return {
        "mode": "scanner",
        "count": len(result),
        "signals": result,
        "message": "Observed momentum scan; not a prediction or recommendation."
    }
