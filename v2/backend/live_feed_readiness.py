"""Read-only, fail-closed NSE screener feed readiness assessment."""


def assess_live_feed(health, *, minimum_recent_stocks=1):
    """Separate observed partial feed activity from full-universe coverage."""
    if not isinstance(health, dict):
        health = {}
    blockers = []
    if health.get("market_session") != "OPEN":
        blockers.append("MARKET_NOT_OPEN")
    if health.get("status") != "REPORTING":
        blockers.append("FEED_NOT_REPORTING")
    recent = health.get("stocks_with_recent_ticks")
    universe = health.get("universe_size")
    valid_recent = type(recent) is int and recent >= 0
    valid_universe = type(universe) is int and universe > 0
    if not valid_recent or recent < minimum_recent_stocks:
        blockers.append("NO_RECENT_VERIFIED_STOCK_TICKS")
    if not valid_universe:
        blockers.append("UNIVERSE_SIZE_UNVERIFIED")
    elif not valid_recent or recent != universe:
        blockers.append("FULL_UNIVERSE_COVERAGE_NOT_VERIFIED")
    if health.get("connection_last_event") != "CONNECTED":
        blockers.append("CONNECTION_EVENT_NOT_VERIFIED")
    activity_observed = (
        health.get("market_session") == "OPEN"
        and health.get("status") == "REPORTING"
        and valid_recent and recent >= minimum_recent_stocks
    )
    return {
        "live_screener_ready": not blockers,
        "partial_feed_activity_observed": activity_observed,
        "full_universe_coverage_verified": (
            valid_recent and valid_universe and recent == universe
            and health.get("status") == "REPORTING"
        ),
        "recent_stock_count": recent if valid_recent else 0,
        "expected_stock_count": universe if valid_universe else None,
        "blockers": blockers,
        "order_execution_enabled": False,
        "note": "Read-only observed tick coverage, not a trade signal or broker order permission",
    }
