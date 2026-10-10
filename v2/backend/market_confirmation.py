"""Pure research-only market direction confirmation. No orders or broker access.

Inputs must be calculated from fresh, completed index candles by a separate
data adapter. Prediction confidence is an evidence score, not win probability.
"""
from dataclasses import dataclass
from decimal import Decimal
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo


@dataclass(frozen=True)
class Confirmation:
    status: str
    reason: str
    direction: str
    candidate: str
    as_of_ist: str


def confirm_direction(*, predicted_direction, evidence_score, index_price,
                      ema9, ema20, momentum, last_candle_ist,
                      support, resistance, now=None, min_evidence_score=60):
    """Return a candidate for MANUAL review only, never a trade instruction.

    Require a fresh completed candle, aligned EMA/momentum, and breakout of
    the supplied support/resistance level. Levels must be independently
    calculated from *prior* completed candles, not the current candle.
    """
    now = now or datetime.now(ZoneInfo("Asia/Kolkata"))
    if now.tzinfo is None or last_candle_ist.tzinfo is None:
        raise ValueError("Timestamps must be timezone-aware")
    now = now.astimezone(ZoneInfo("Asia/Kolkata"))
    candle = last_candle_ist.astimezone(ZoneInfo("Asia/Kolkata"))
    stamp = now.isoformat()
    def result(status, reason, direction="NONE", candidate="NONE"):
        return Confirmation(status, reason, direction, candidate, stamp)

    if predicted_direction not in ("BULLISH", "BEARISH", "NEUTRAL", "UNKNOWN"):
        raise ValueError("Invalid predicted direction")
    if type(evidence_score) is not int or not 0 <= evidence_score <= 100:
        raise ValueError("Evidence score must be an integer from 0 to 100")
    if not isinstance(min_evidence_score, int) or not 0 <= min_evidence_score <= 100:
        raise ValueError("Invalid minimum evidence score")
    if candle > now or now - candle > timedelta(minutes=3):
        return result("WAIT", "STALE_OR_FUTURE_CANDLE")
    if candle.date() != now.date():
        return result("WAIT", "PREVIOUS_SESSION_CANDLE")
    if now.weekday() >= 5 or not (9 <= now.hour <= 15):
        return result("WAIT", "MARKET_CLOSED")
    minute = now.hour * 60 + now.minute
    if not (9 * 60 + 20 <= minute < 15 * 60):
        return result("WAIT", "OUTSIDE_NEW_ENTRY_WINDOW")
    if predicted_direction in ("UNKNOWN", "NEUTRAL") or evidence_score < min_evidence_score:
        return result("WAIT", "INSUFFICIENT_PREMARKET_EVIDENCE")

    values = [index_price, ema9, ema20, momentum, support, resistance]
    try:
        numbers = [Decimal(str(v)) for v in values]
    except (ValueError, TypeError, ArithmeticError):
        return result("WAIT", "DATA_UNAVAILABLE")
    if not all(v.is_finite() for v in numbers):
        return result("WAIT", "DATA_UNAVAILABLE")
    price, fast, slow, mom, sup, res = numbers
    if not (price > 0 and sup > 0 and res > sup):
        return result("WAIT", "INVALID_PRICE_LEVELS")

    bullish = price > res and fast > slow and mom > 0
    bearish = price < sup and fast < slow and mom < 0
    if predicted_direction == "BULLISH":
        if bearish:
            return result("INVALIDATED", "CONFIRMED_BEARISH_BREAKDOWN", "BEARISH")
        if bullish:
            return result("CANDIDATE", "BULLISH_BREAKOUT_CONFIRMED", "BULLISH", "CE")
    else:
        if bullish:
            return result("INVALIDATED", "CONFIRMED_BULLISH_BREAKOUT", "BULLISH")
        if bearish:
            return result("CANDIDATE", "BEARISH_BREAKDOWN_CONFIRMED", "BEARISH", "PE")
    return result("WAIT", "NO_CONFIRMED_BREAKOUT")
