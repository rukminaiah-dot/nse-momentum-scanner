"""Read-only option-chain ranking for MANUAL review; never places orders.

The caller must supply current, timestamped broker option-chain snapshots and
verified contract lot sizes. Missing quotes/greeks are not invented.
"""
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation
from zoneinfo import ZoneInfo

from .option_risk import assess_long_option


@dataclass(frozen=True)
class Selection:
    status: str
    reason: str
    contract: dict | None
    candidates_checked: int


def _number(value):
    try:
        n = Decimal(str(value))
        return n if n.is_finite() else None
    except (InvalidOperation, ValueError, TypeError):
        return None


def select_option(*, direction, spot, contracts, capital=20000,
                  remaining_daily_risk=1200, now=None,
                  max_spread_pct=Decimal("0.03"),
                  min_volume=100, min_open_interest=500):
    """Rank ATM/one-step ITM long CE or PE by spread, volume, and OI.

    Each contract must provide: type (CE/PE), strike, expiry (YYYY-MM-DD),
    bid, ask, lot_size, volume, open_interest, updated_at (aware datetime),
    stop and target (per-unit premium, independently calculated).
    The returned candidate is NOT a buy signal or a verified prediction.
    """
    now = now or datetime.now(ZoneInfo("Asia/Kolkata"))
    if now.tzinfo is None:
        raise ValueError("now must be timezone-aware")
    now = now.astimezone(ZoneInfo("Asia/Kolkata"))
    if direction not in ("BULLISH", "BEARISH"):
        return Selection("NO_TRADE", "NO_CONFIRMED_DIRECTION", None, 0)
    if not isinstance(contracts, (list, tuple)):
        raise TypeError("contracts must be a list or tuple")
    spot = _number(spot)
    if spot is None or spot <= 0:
        return Selection("NO_TRADE", "INVALID_SPOT", None, 0)
    if not contracts:
        return Selection("NO_TRADE", "OPTION_CHAIN_UNAVAILABLE", None, 0)

    option_type = "CE" if direction == "BULLISH" else "PE"
    strikes = sorted({s for row in contracts if isinstance(row, dict)
                      and row.get("type") == option_type
                      if (s := _number(row.get("strike"))) is not None and s > 0})
    if not strikes:
        return Selection("NO_TRADE", "NO_MATCHING_CONTRACTS", None, len(contracts))
    atm = min(strikes, key=lambda s: (abs(s - spot), s))
    itm = max((s for s in strikes if s < atm), default=None) if option_type == "CE" else min(
        (s for s in strikes if s > atm), default=None)
    eligible_strikes = {atm, itm}
    eligible_strikes.discard(None)
    ranked = []
    for row in contracts:
        if not isinstance(row, dict) or row.get("type") != option_type:
            continue
        strike = _number(row.get("strike"))
        if strike not in eligible_strikes:
            continue
        ts = row.get("updated_at")
        if not isinstance(ts, datetime) or ts.tzinfo is None:
            continue
        age = now - ts.astimezone(ZoneInfo("Asia/Kolkata"))
        if age < timedelta(0) or age > timedelta(minutes=3):
            continue
        try:
            expiry = datetime.strptime(row["expiry"], "%Y-%m-%d").date()
        except (KeyError, ValueError, TypeError):
            continue
        if expiry < now.date():
            continue
        bid, ask = _number(row.get("bid")), _number(row.get("ask"))
        volume, oi = _number(row.get("volume")), _number(row.get("open_interest"))
        stop, target = _number(row.get("stop")), _number(row.get("target"))
        lot = row.get("lot_size")
        if (any(v is None for v in (bid, ask, volume, oi, stop, target))
                or bid <= 0 or ask <= bid or volume < min_volume or oi < min_open_interest
                or type(lot) is not int or lot <= 0):
            continue
        spread = (ask - bid) / ask
        if spread > _number(max_spread_pct):
            continue
        try:
            assessment = assess_long_option(
                capital=capital, entry=ask, stop=stop, target=target,
                lot_size=lot, remaining_daily_risk=remaining_daily_risk,
                estimated_total_costs=row.get("estimated_total_costs", 0))
        except (ValueError, TypeError, InvalidOperation, ZeroDivisionError):
            continue
        if assessment.decision != "ELIGIBLE_FOR_MANUAL_REVIEW":
            continue
        ranked.append((spread, -volume, -oi, abs(strike - spot), row, assessment))

    if not ranked:
        return Selection("NO_TRADE", "NO_CONTRACT_PASSES_LIQUIDITY_AND_RISK", None, len(contracts))
    ranked.sort(key=lambda item: item[:4])
    spread, _, _, _, row, risk = ranked[0]
    return Selection("MANUAL_REVIEW", "CONTRACT_PASSES_FILTERS_NOT_A_TRADE_SIGNAL", {
        "type": row["type"], "strike": str(row["strike"]), "expiry": row["expiry"],
        "entry_ask": str(row["ask"]), "lot_size": row["lot_size"],
        "spread_pct": str((spread * 100).quantize(Decimal("0.01"))),
        "investment": str(risk.investment), "planned_loss": str(risk.planned_loss),
        "potential_profit": str(risk.potential_profit),
        "potential_return_pct": str(risk.return_pct.quantize(Decimal("0.01"))),
        "reward_risk": str(risk.reward_risk.quantize(Decimal("0.01"))),
    }, len(contracts))
