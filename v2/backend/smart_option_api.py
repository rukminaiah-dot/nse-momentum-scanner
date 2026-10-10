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

    # PostgreSQL is an optional fallback for lost ephemeral SQLite rows.
    # Archived candles remain subject to the same timestamp freshness check.
    archive_status = "NOT_CHECKED"
    if len(snapshots) < 2:
        try:
            from .index_snapshot_archive import read_index_snapshots
            archived = read_index_snapshots()
            for symbol, row in archived.items():
                if symbol not in snapshots or snapshots[symbol].get("price") is None:
                    snapshots[symbol] = row
            archive_status = "READ_OK"
        except Exception:
            archive_status = "READ_ERROR"

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
        "capital_inr": None,
        "maximum_investment_inr": None,
        "maximum_planned_loss_inr": None,
        "minimum_reward_risk": None,
        "allocation_policy": "FLEXIBLE_WITH_RISK_REVIEW",
        "selection_priority": "BEST_VERIFIED_OPTION_SETUP",
        "new_entry_cutoff_ist": "15:00",
        "monitor_until_ist": "15:15",
        "data_sources": {
            "premarket_evidence": "NOT_CONNECTED",
            "live_index_confirmation": "NOT_CONNECTED",
            "live_option_chain": "NOT_CONNECTED",
        },
        "database_status": database_status,
        "archive_status": archive_status,
        "index_rows_found": len(snapshots),
        "indices": [index_row(name) for name in ("NIFTY 50", "SENSEX")],
    }


@router.get("/api/v2/upstox-option-chain-check")
def upstox_option_chain_check(index: str = "NIFTY 50"):
    """On-demand, read-only diagnostic; never return quotes or credentials."""
    if index not in ("NIFTY 50", "SENSEX"):
        return {"status": "INVALID_INDEX", "supported_indices": ["NIFTY 50", "SENSEX"],
                "order_execution_enabled": False}
    try:
        from .upstox_option_chain import fetch_option_chain
        result = fetch_option_chain(index)
        return {
            "index": index,
            "status": result["status"],
            "reason": result.get("reason"),
            "expiry": result.get("expiry"),
            "contracts_found": len(result.get("contracts", [])),
            "quote_freshness": "UNVERIFIED",
            "trade_status": "NO_TRADE",
            "order_execution_enabled": False,
        }
    except Exception as exc:
        from .upstox_option_chain import OptionDataError
        reason = str(exc) if isinstance(exc, OptionDataError) else "UPSTOX_DIAGNOSTIC_ERROR"
        return {"index": index, "status": "READ_ERROR", "reason": reason,
                "contracts_found": 0, "quote_freshness": "UNVERIFIED",
                "trade_status": "NO_TRADE", "order_execution_enabled": False}


@router.get("/api/v2/upstox-auth-check")
def upstox_auth_check():
    """Read-only credential diagnostic; exposes only HTTP status categories.

    Profile endpoint tests basic bearer-token access separately from option
    contract entitlement. Never return the profile, token, or response body.
    """
    import os
    from urllib.error import HTTPError, URLError
    from urllib.request import Request, urlopen

    token = os.environ.get("UPSTOX_ACCESS_TOKEN")
    result = {"status": "NOT_CHECKED", "reason": None,
              "token_configured": bool(token),
              "trade_status": "NO_TRADE", "order_execution_enabled": False}
    if not token:
        result.update(status="NOT_CONNECTED", reason="TOKEN_MISSING")
        return result
    request = Request(
        "https://api.upstox.com/v2/user/profile",
        headers={"Authorization": "Bearer " + token, "Accept": "application/json"},
    )
    try:
        with urlopen(request, timeout=8) as response:
            result.update(status="AUTH_HTTP_OK" if response.status == 200 else "AUTH_UNEXPECTED_RESPONSE",
                          reason="PROFILE_ENDPOINT_HTTP_" + str(response.status))
    except HTTPError as exc:
        result.update(status="AUTH_HTTP_ERROR", reason="PROFILE_ENDPOINT_HTTP_" + str(exc.code))
    except (URLError, TimeoutError, OSError):
        result.update(status="AUTH_NETWORK_ERROR", reason="PROFILE_ENDPOINT_UNREACHABLE")
    return result
