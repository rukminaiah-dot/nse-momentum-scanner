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
    if (isinstance(neutral_band_pct, bool) or not isinstance(neutral_band_pct, (int, float)) or not isfinite(neutral_band_pct) or neutral_band_pct < 0 or not isfinite(change_pct)):
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
                              now=None, max_age_minutes=1440, session_date_ist=None, expected_previous_session_date_ist=None):
    """Classify a *supplied* previous-session open-to-close move.

    Timestamp freshness alone does not establish exchange-session provenance.
    Callers must verify the trading date and source before using this evidence.
    """
    now = now or datetime.now(IST)
    # Expected date must be verified against an exchange calendar by the caller.
    if (not isinstance(session_date_ist, str)
            or not isinstance(expected_previous_session_date_ist, str)
            or session_date_ist != expected_previous_session_date_ist):
        return None
    try:
        from datetime import date
        if date.fromisoformat(session_date_ist).isoformat() != session_date_ist:
            return None
    except ValueError:
        return None
    if not _valid_observation(observed_at_ist, now, max_age_minutes):
        return None
    if any(isinstance(x, bool) or not isinstance(x, (float, int)) or not isfinite(x) or x <= 0
           for x in (previous_open, previous_close)):
        return None
    return classify_percentage_change((previous_close / previous_open - 1) * 100)


def global_markets_evidence(*, market_changes_pct, observed_at_ist, now=None):
    now = now or datetime.now(IST)
    if not _valid_observation(observed_at_ist, now, 30):
        return None
    if not isinstance(market_changes_pct, dict) or len(market_changes_pct) < 2:
        return None
    if any(not isinstance(k, str) or not k.strip() for k in market_changes_pct):
        return None
    values = list(market_changes_pct.values())
    if any(isinstance(v, bool) or not isinstance(v, (int, float)) or not isfinite(v) for v in values):
        return None
    return classify_percentage_change(sum(values) / len(values))


def fii_dii_evidence(*, fii_net_crore, dii_net_crore, observed_at_ist,
                     session_date_ist, expected_previous_session_date_ist, now=None):
    now = now or datetime.now(IST)
    if not isinstance(session_date_ist, str) or session_date_ist != expected_previous_session_date_ist:
        return None
    try:
        from datetime import date
        if date.fromisoformat(session_date_ist).isoformat() != session_date_ist:
            return None
    except ValueError:
        return None
    if not _valid_observation(observed_at_ist, now, 1440):
        return None
    values = (fii_net_crore, dii_net_crore)
    if any(isinstance(v, bool) or not isinstance(v, (int, float)) or not isfinite(v) for v in values):
        return None
    total = sum(values)
    return 1 if total > 0 else -1 if total < 0 else 0


def rbi_macro_news_evidence(*, event_bias, event_id, observed_at_ist, now=None):
    now = now or datetime.now(IST)
    if not isinstance(event_id, str) or not event_id.strip():
        return None
    if not _valid_observation(observed_at_ist, now, 240):
        return None
    return event_bias if type(event_bias) is int and event_bias in (-1, 0, 1) else None


def assess_verified_sources(observations, *, now=None):
    """Assemble evidence only from explicitly source-verified observations.

    Each source entry requires verified=True and a supported observation shape.
    No implicit conversion of unavailable sources into neutral votes.
    """
    from .premarket_prediction import WEIGHTS, assess_premarket

    now = now or datetime.now(IST)
    if not isinstance(observations, dict):
        raise TypeError("observations must be a dictionary")
    if set(observations) - set(WEIGHTS):
        raise ValueError("Unknown premarket source")

    evidence = {}
    sources = {}
    for key, weight in WEIGHTS.items():
        record = observations.get(key)
        value = None
        if (isinstance(record, dict) and record.get("verified") is True
                and isinstance(record.get("source"), str) and bool(record["source"].strip())
                and isinstance(record.get("instrument"), str) and bool(record["instrument"].strip())
                and record.get("session_verified") is True):
            if key == "gift_nifty":
                value = gift_nifty_evidence(
                    last_price=record.get("last_price"),
                    reference_close=record.get("reference_close"),
                    observed_at_ist=record.get("observed_at_ist"), now=now)
            elif key == "previous_session":
                value = previous_session_evidence(
                    previous_open=record.get("previous_open"),
                    previous_close=record.get("previous_close"),
                    observed_at_ist=record.get("observed_at_ist"), now=now,
                    session_date_ist=record.get("session_date_ist"),
                    expected_previous_session_date_ist=record.get("expected_previous_session_date_ist"))
            elif key == "global_markets":
                value = global_markets_evidence(
                    market_changes_pct=record.get("market_changes_pct"),
                    observed_at_ist=record.get("observed_at_ist"), now=now)
            elif key == "fii_dii":
                value = fii_dii_evidence(
                    fii_net_crore=record.get("fii_net_crore"),
                    dii_net_crore=record.get("dii_net_crore"),
                    observed_at_ist=record.get("observed_at_ist"),
                    session_date_ist=record.get("session_date_ist"),
                    expected_previous_session_date_ist=record.get("expected_previous_session_date_ist"),
                    now=now)
            elif key == "rbi_macro_news":
                value = rbi_macro_news_evidence(
                    event_bias=record.get("event_bias"),
                    event_id=record.get("event_id"),
                    observed_at_ist=record.get("observed_at_ist"), now=now)
        if value is not None:
            evidence[key] = value
        status = ("VERIFIED" if value is not None else
                  "NOT_CONNECTED" if record is None else "INVALID_OR_UNVERIFIED")
        sources[key] = {
            "weight": weight,
            "value": value,
            "status": status,
            "observed_at_ist": record.get("observed_at_ist") if value is not None else None,
        }
    prediction = assess_premarket(evidence, now=now)
    return prediction, sources
