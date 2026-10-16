"""Conservative operational checklist for research-only pre-market readiness."""
from .premarket_prediction import WEIGHTS


def premarket_readiness(prediction, sources):
    """Never infer readiness from partial, stale or manually entered votes."""
    blockers = []
    for key in WEIGHTS:
        record = sources.get(key) if isinstance(sources, dict) else None
        if not isinstance(record, dict) or record.get("status") != "VERIFIED":
            blockers.append("SOURCE_NOT_VERIFIED:" + key)
    if prediction.status != "WAIT_LIVE_CONFIRMATION":
        blockers.append("EVIDENCE_INCOMPLETE")
    # Verified premarket data is not a live-session trade confirmation.
    return {
        "research_forecast_ready": not blockers,
        "trade_signal_ready": False,
        "live_market_confirmation": "NOT_CONNECTED",
        "blockers": blockers + ["LIVE_MARKET_CONFIRMATION_REQUIRED"],
        "order_execution_enabled": False,
    }
