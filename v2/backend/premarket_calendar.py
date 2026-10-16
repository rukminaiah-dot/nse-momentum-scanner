"""Fail-closed NSE session calendar validation for research-only premarket data.

This module consumes an externally verified list of NSE trading dates. It does
not invent a holiday calendar or fetch one implicitly.
"""
from datetime import date


def previous_trading_session_date(*, target_date_ist, verified_session_dates, calendar_verified=False, calendar_source=None):
    """Return prior session ISO date only if a verified schedule covers target date.

    Dates must be strictly increasing, unique ISO YYYY-MM-DD strings. The caller
    must supply a complete, authoritative calendar covering the requested range.
    """
    if (calendar_verified is not True or not isinstance(calendar_source, str) or not calendar_source.strip()):
        return None
    if not isinstance(target_date_ist, str):
        return None
    try:
        target = date.fromisoformat(target_date_ist)
        if target.isoformat() != target_date_ist:
            return None
    except ValueError:
        return None
    if not isinstance(verified_session_dates, (list, tuple)) or len(verified_session_dates) < 2:
        return None
    try:
        dates = [date.fromisoformat(value) for value in verified_session_dates]
    except (TypeError, ValueError):
        return None
    if any(not isinstance(value, str) or day.isoformat() != value
           for value, day in zip(verified_session_dates, dates)):
        return None
    if any(a >= b for a, b in zip(dates, dates[1:])):
        return None
    # A verified schedule must explicitly include the target session.
    if target not in dates:
        return None
    index = dates.index(target)
    return dates[index - 1].isoformat() if index > 0 else None
