"""Pure, offline adapters for explicitly supplied, timestamped market observations.

No external requests, credentials, orders, or implicit live-data claims.
"""
from datetime import datetime, timedelta
from math import isfinite
from zoneinfo import ZoneInfo

IST = ZoneInfo("Asia/Kolkata")


def _valid_observation(observed_at_ist, now, max_age_minutes):
    if not isinstance(observed_at_ist, str):
        return False
    try:
        observed = datetime.fromisoformat(observed_at_ist)
    except ValueError:
        return False
    if observed.tzinfo is None:
        return False
    age = now.astimezone(IST) - observed.astimezone(IST)
    return timedelta(0) <= age <= timedelta(minutes=max_age_minutes)


def classify_percentage_change(change_pct, *, neutral_band_pct=0.15):
    """Return -1, 0 or 1 for a finite percentage change, else None."""
    if isinstance(change_pct, bool) or not isinstance(change_pct, (float, int)):
        return None
    if not isfinite(change_pct) or neutral_band_pct < 0:
        return None
    return 1 if change_pct > neutral_band_pct else -1 if change_pct < -neutral_band_pct else 0


def gift_nifty_evidence(*, last_price, reference_close, observed_at_ist,
                        now=None, max_age_minutes=15):
    """Classify a *supplied* GIFT NIFTY quote against a verified reference close.

    Does not fetch quotes or assert that a particular contract/reference is valid.
    """
    now = now or datetime.now(IST)
    if not _valid_observation(observed_at_ist, now, max_age_minutes):
        return None
    if any(isinstance(x, bool) or not isinstance(x, (float, int)) or not isfinite(x) or x <= 0
           for x in (last_price, reference_close)):
        return None
    return classify_percentage_change((last_price / reference_close - 1) * 100)


def previous_session_evidence(*, previous_open, previous_close, observed_at_ist,
                              now=None, max_age_minutes=1440):
    """Classify a *supplied* previous-session open-to-close move.

    Timestamp freshness alone does not establish exchange-session provenance.
    Callers must verify the trading date and source before using this evidence.
    """
    now = now or datetime.now(IST)
    if not _valid_observation(observed_at_ist, now, max_age_minutes):
        return None
    if any(isinstance(x, bool) or not isinstance(x, (float, int)) or not isfinite(x) or x <= 0
           for x in (previous_open, previous_close)):
        return None
    return classify_percentage_change((previous_close / previous_open - 1) * 100)
