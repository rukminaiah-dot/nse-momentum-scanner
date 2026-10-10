"""Research-only pre-market bias assessment. No orders, no invented market data."""
from dataclasses import dataclass
from datetime import datetime
from zoneinfo import ZoneInfo

WEIGHTS = {
    "gift_nifty": 3,
    "global_markets": 2,
    "rbi_macro_news": 3,
    "fii_dii": 1,
    "previous_session": 1,
}


@dataclass(frozen=True)
class Prediction:
    direction: str
    evidence_score: int
    status: str
    reasons: tuple[str, ...]
    as_of_ist: str


def assess_premarket(evidence: dict, *, now=None) -> Prediction:
    """Evidence values must be -1 (bearish), 0 (neutral), or 1 (bullish).

    This score measures agreement among supplied evidence, NOT win probability.
    Missing evidence is never treated as neutral. No trade signal is produced.
    """
    now = now or datetime.now(ZoneInfo("Asia/Kolkata"))
    if now.tzinfo is None:
        raise ValueError("now must be timezone-aware")
    stamp = now.astimezone(ZoneInfo("Asia/Kolkata")).isoformat()
    if not isinstance(evidence, dict):
        raise TypeError("evidence must be a dictionary")
    if any(key not in WEIGHTS for key in evidence):
        raise ValueError("Unknown evidence category")
    if any(type(value) is not int or value not in (-1, 0, 1) for value in evidence.values()):
        raise ValueError("Evidence values must be -1, 0 or 1")

    missing = [key for key in WEIGHTS if key not in evidence]
    if missing:
        return Prediction("UNKNOWN", 0, "WAIT_DATA_UNAVAILABLE",
                          tuple("Missing: " + key for key in missing), stamp)

    weighted = sum(WEIGHTS[key] * evidence[key] for key in WEIGHTS)
    max_weight = sum(WEIGHTS.values())
    score = round(abs(weighted) / max_weight * 100)
    direction = "BULLISH" if weighted > 0 else "BEARISH" if weighted < 0 else "NEUTRAL"
    reasons = tuple(f"{key}: {('bullish' if evidence[key] > 0 else 'bearish' if evidence[key] < 0 else 'neutral')}" for key in WEIGHTS)
    return Prediction(direction, score, "WAIT_LIVE_CONFIRMATION", reasons, stamp)
