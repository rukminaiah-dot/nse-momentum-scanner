"""Read-only Smart Option Buyer API.

No live option-chain or news provider is wired yet. Fail closed rather than
fabricating predictions, quotes, returns, or entry recommendations.
"""
from datetime import datetime, timedelta
import sqlite3
from .database import DB_PATH
from zoneinfo import ZoneInfo

from fastapi import APIRouter

router = APIRouter()


@router.get("/api/v2/smart-option-buyer")
def smart_option_buyer():
    now = datetime.now(ZoneInfo("Asia/Kolkata"))
    # Read existing index snapshots only; never initiate broker connections.
    snapshots = {}
    database_status = "UNAVAILABLE"
    try:
        with sqlite3.connect(DB_PATH, timeout=3) as db:
            db.row_factory = sqlite3.Row
            rows = db.execute(
                "SELECT symbol, updated_at, price, ema9, ema20, momentum "
                "FROM scanner_results WHERE symbol IN ('NIFTY 50','SENSEX')"
            ).fetchall()
            snapshots = {r["symbol"]: dict(r) for r in rows}
            database_status = "READ_OK"
    except (sqlite3.Error, OSError):
        database_status = "READ_ERROR"

    def index_row(name):
        row = snapshots.get(name)
        diagnostic = {"index": name, "prediction": "UNAVAILABLE",
                      "evidence_score": None, "confirmation": "WAIT",
                      "option_candidate": None, "investment_inr": None,
                      "planned_loss_inr": None, "potential_profit_inr": None,
                      "status": "NO_TRADE", "reason": "LIVE_DATA_INTEGRATION_PENDING",
                      "index_price": None, "index_candle_ist": None,
                      "index_data_status": "UNAVAILABLE"}
        if not row:
            return diagnostic
        diagnostic["index_price"] = row.get("price")
        diagnostic["index_candle_ist"] = row.get("updated_at")
        try:
            # Existing scanner persists naive timestamps in IST.
            stamp = datetime.strptime(row["updated_at"], "%Y-%m-%d %H:%M:%S")
            stamp = stamp.replace(tzinfo=ZoneInfo("Asia/Kolkata"))
            age = now - stamp
            fresh = timedelta(0) <= age <= timedelta(minutes=3) and stamp.date() == now.date()
            diagnostic["index_data_status"] = "FRESH_CANDLE" if fresh else "STALE_CANDLE"
        except (ValueError, TypeError):
            diagnostic["index_data_status"] = "INVALID_TIMESTAMP"
        return diagnostic

    return {
        "mode": "MANUAL_RESEARCH_ONLY",
        "order_execution_enabled": False,
        "as_of_ist": now.isoformat(),
        "capital_inr": 20000,
        "maximum_investment_inr": 6000,
        "maximum_planned_loss_inr": 1200,
        "minimum_reward_risk": 2,
        "new_entry_cutoff_ist": "15:00",
        "monitor_until_ist": "15:15",
        "data_sources": {
            "premarket_evidence": "NOT_CONNECTED",
            "live_index_confirmation": "NOT_CONNECTED",
            "live_option_chain": "NOT_CONNECTED",
        },
        "database_status": database_status,
        "index_rows_found": len(snapshots),
        "indices": [index_row(name) for name in ("NIFTY 50", "SENSEX")],
    }
