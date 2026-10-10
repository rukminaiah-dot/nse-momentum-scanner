"""Read-only Smart Option Buyer API.

No live option-chain or news provider is wired yet. Fail closed rather than
fabricating predictions, quotes, returns, or entry recommendations.
"""
from datetime import datetime
from zoneinfo import ZoneInfo

from fastapi import APIRouter

router = APIRouter()


@router.get("/api/v2/smart-option-buyer")
def smart_option_buyer():
    now = datetime.now(ZoneInfo("Asia/Kolkata"))
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
        "indices": [
            {
                "index": name,
                "prediction": "UNAVAILABLE",
                "evidence_score": None,
                "confirmation": "WAIT",
                "option_candidate": None,
                "investment_inr": None,
                "planned_loss_inr": None,
                "potential_profit_inr": None,
                "status": "NO_TRADE",
                "reason": "LIVE_DATA_INTEGRATION_PENDING",
            }
            for name in ("NIFTY 50", "SENSEX")
        ],
    }
