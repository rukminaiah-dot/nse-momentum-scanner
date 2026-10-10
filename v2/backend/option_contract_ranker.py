"""Read-only option contract ranking. No broker access or order execution.

Candidates must come from a verified, timestamped option-chain feed.
Scores rank contract quality, not probability of profit.
"""
from datetime import datetime, timedelta
from math import isfinite
from zoneinfo import ZoneInfo

IST = ZoneInfo("Asia/Kolkata")
INDEXES = {"NIFTY 50", "SENSEX"}


def rank_option_candidates(index, direction, contracts, *, quote_time, now=None):
    """Return a research shortlist or a fail-closed WAIT response.

    Required contract keys: strike, expiry, type, bid, ask, volume,
    open_interest. Prices are in INR per index point. Lot size is mandatory
    for cost estimates. All numeric values must be valid and nonnegative.
    """
    wait = lambda reason: {"status": "NO_TRADE", "reason": reason, "candidates": []}
    if index not in INDEXES or direction not in ("BULLISH", "BEARISH"):
        return wait("DIRECTION_NOT_CONFIRMED")
    if not isinstance(quote_time, datetime) or quote_time.tzinfo is None:
        return wait("UNVERIFIED_QUOTE_TIME")
    now = now or datetime.now(IST)
    if now.tzinfo is None:
        return wait("INVALID_NOW")
    now, quote_time = now.astimezone(IST), quote_time.astimezone(IST)
    if now.weekday() >= 5 or quote_time.date() != now.date() or not (timedelta(0) <= now - quote_time <= timedelta(minutes=2)):
        return wait("STALE_OR_CLOSED_MARKET")
    if not isinstance(contracts, (list, tuple)) or not contracts:
        return wait("OPTION_CHAIN_NOT_CONNECTED")
    option_type = "CE" if direction == "BULLISH" else "PE"
    shortlisted = []
    for c in contracts:
        if not isinstance(c, dict) or c.get("type") != option_type:
            continue
        try:
            bid, ask = float(c["bid"]), float(c["ask"])
            strike = float(c["strike"])
            volume, oi = float(c["volume"]), float(c["open_interest"])
            lot = int(c["lot_size"])
            expiry = datetime.strptime(str(c["expiry"]), "%Y-%m-%d").date()
        except (KeyError, TypeError, ValueError, OverflowError):
            continue
        if not all(isfinite(v) for v in (bid, ask, strike, volume, oi)):
            continue
        if bid <= 0 or ask <= bid or strike <= 0 or volume < 100 or oi < 1000 or lot <= 0 or expiry < now.date():
            continue
        spread_pct = (ask - bid) / ((ask + bid) / 2) * 100
        if spread_pct > 2:
            continue
        # Liquidity-first deterministic ranking; never implies expected return.
        score = round(100 - spread_pct * 20 + min(volume / 10000, 10) + min(oi / 100000, 10), 2)
        shortlisted.append({
            "index": index, "type": option_type, "strike": strike,
            "expiry": expiry.isoformat(), "bid": bid, "ask": ask,
            "spread_pct": round(spread_pct, 2), "lot_size": lot,
            "estimated_one_lot_premium_inr": round(ask * lot, 2),
            "quality_score": score,
        })
    shortlisted.sort(key=lambda x: (-x["quality_score"], x["estimated_one_lot_premium_inr"], x["expiry"], x["strike"]))
    if not shortlisted:
        return wait("NO_LIQUID_CONTRACTS")
    return {
        "status": "RESEARCH_SHORTLIST_ONLY",
        "reason": "LIVE_CONFIRMATION_AND_RISK_REVIEW_REQUIRED",
        "quote_time_ist": quote_time.isoformat(),
        "candidates": shortlisted[:3],
        "order_execution_enabled": False,
    }
