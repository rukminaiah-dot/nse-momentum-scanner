"""Read-only fail-closed NSE screener feed readiness assessment."""


def assess_live_feed(health, *, minimum_recent_stocks=1):
    """A heartbeat alone never proves that tradable market ticks are arriving."""
    blockers = []
    if not isinstance(health, dict):
        health = {}
    if health.get("market_session") != "OPEN":
        blockers.append("MARKET_NOT_OPEN")
    if health.get("status") != "REPORTING":
        blockers.append("FEED_NOT_REPORTING")
    recent = health.get("stocks_with_recent_ticks")
    if isinstance(recent, bool) or not isinstance(recent, int) or recent < minimum_recent_stocks:
        blockers.append("NO_RECENT_VERIFIED_STOCK_TICKS")
    return {
        "live_screener_ready": not blockers,
        "recent_stock_count": recent if type(recent) is int and recent >= 0 else 0,
        "blockers": blockers,
        "order_execution_enabled": False,
        "note": "Read-only feed evidence, not a trade signal or broker order permission",
    }
