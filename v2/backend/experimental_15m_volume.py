"""Strict 15-minute same-slot volume baseline for PAPER research only.

Input: completed historical 15-minute OHLCV bars (dicts) with timestamps at
15-minute candle START in IST local time. No estimated or partial baseline.
"""
from datetime import timedelta
from math import isfinite


def verified_15m_same_slot_average(current_bar, historical_bars, *, sessions=20, require_full_sessions=False):
    if not isinstance(sessions, int) or isinstance(sessions, bool) or sessions < 1:
        raise ValueError("sessions must be a positive integer")
    try:
        stamp = current_bar["timestamp"]
        if (stamp.hour * 60 + stamp.minute - (9 * 60 + 15)) % 15 != 0:
            return None
        if not (9 * 60 + 15 <= stamp.hour * 60 + stamp.minute < 15 * 60 + 30):
            return None
        if require_full_sessions:
            dates = sorted({b['timestamp'].date() for b in historical_bars
                            if b['timestamp'].date() < stamp.date() and b['timestamp'].weekday() < 5})[-sessions:]
            if len(dates) != sessions:
                return None
            for day in dates:
                rows = [b for b in historical_bars if b['timestamp'].date() == day]
                slots = [(b['timestamp'].hour * 60 + b['timestamp'].minute) for b in rows]
                if len(rows) != 25 or set(slots) != set(range(555, 930, 15)) or any(b['timestamp'].second or b['timestamp'].microsecond for b in rows):
                    return None
                for b in rows:
                    values = [float(b[k]) for k in ('open','high','low','close','volume')]
                    opn, high, low, close, volume = values
                    if not all(isfinite(v) for v in values) or min(opn,high,low,close) <= 0 or volume < 0 or high < max(opn,close) or low > min(opn,close):
                        return None
            historical_bars = [b for b in historical_bars if b['timestamp'].date() in dates]
        by_day = {}
        for bar in historical_bars:
            prior = bar["timestamp"]
            if prior.date() >= stamp.date() or prior.weekday() >= 5 or (prior.hour, prior.minute) != (stamp.hour, stamp.minute):
                continue
            volume = float(bar["volume"])
            if not isfinite(volume) or volume < 0:
                continue
            # One observation per session and slot. Duplicate records are
            # ambiguous and must not silently overwrite a valid observation.
            day = prior.date()
            if day in by_day:
                return None
            by_day[day] = volume
        days = sorted(by_day)[-sessions:]
        if len(days) != sessions:
            return None
        baseline = sum(by_day[day] for day in days) / sessions
        return baseline if baseline > 0 and isfinite(baseline) else None
    except (KeyError, TypeError, ValueError, AttributeError, OverflowError):
        return None


def evaluate_with_15m_volume(bars, historical_15m_bars, *, now, settings=None):
    """Isolated paper-only adapter; never called by production scanner."""
    from .experimental_15m_stoch_rsi import Settings, evaluate
    if not bars:
        return {"signal": "WAIT", "mode": "PAPER", "reason": "INSUFFICIENT_15M_HISTORY"}
    baseline = verified_15m_same_slot_average(bars[-1], historical_15m_bars)
    return evaluate(bars, now=now, same_slot_average_volume=baseline,
                    settings=settings if settings is not None else Settings())
