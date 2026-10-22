"""Paper-only NSE 200 two-stage volume-first research pipeline.

Caller supplies completed 15-minute OHLCV history per symbol and the prior
20-session same-slot history. No broker calls, orders, or production imports.
"""
from math import isfinite

from .experimental_15m_stoch_rsi import Settings, evaluate
from .experimental_15m_volume import verified_15m_same_slot_average


def screen_universe(stock_bars, historical_volume_bars, *, now,
                    min_rvol=1.5, settings=None):
    """Return volume-ranked eligible symbols, evaluated signals and exclusions.

    stock_bars: {symbol: chronological completed 15m candle dicts}
    historical_volume_bars: {symbol: chronological completed prior-session
    15m candle dicts}. The volume gate is applied BEFORE indicators.
    """
    if not isinstance(min_rvol, (int, float)) or not isfinite(min_rvol) or not 0 < min_rvol < 100:
        raise ValueError("min_rvol must be positive and below 100")
    settings = settings or Settings(min_rvol=min_rvol)
    selected = []
    excluded = {}
    for symbol, bars in stock_bars.items():
        if not bars:
            excluded[symbol] = "NO_COMPLETED_15M_CANDLES"
            continue
        latest = bars[-1]
        try:
            stamps = [bar["timestamp"] for bar in bars]
            if len(set(stamps)) != len(stamps):
                excluded[symbol] = "DUPLICATE_15M_CANDLE"
                continue
            close_time = latest["timestamp"]
            age = (now - close_time).total_seconds() / 60 - 15
            if age < 0 or age > settings.max_age_minutes:
                excluded[symbol] = "STALE_OR_INCOMPLETE_15M_CANDLE"
                continue
            current_volume = float(latest["volume"])
            if not isfinite(current_volume) or current_volume < 0:
                excluded[symbol] = "INVALID_CURRENT_VOLUME"
                continue
        except (KeyError, TypeError, ValueError, AttributeError):
            excluded[symbol] = "INVALID_CURRENT_CANDLE"
            continue
        baseline = verified_15m_same_slot_average(
            latest, historical_volume_bars.get(symbol, ()))
        if baseline is None:
            excluded[symbol] = "MISSING_VERIFIED_20_SESSION_VOLUME_BASELINE"
            continue
        rvol = current_volume / baseline
        if rvol < min_rvol:
            excluded[symbol] = "VOLUME_BELOW_THRESHOLD"
            continue
        selected.append((symbol, rvol, baseline, bars))
    selected.sort(key=lambda entry: (-entry[1], entry[0]))
    analyzed = []
    for symbol, rvol, baseline, bars in selected:
        result = evaluate(bars, now=now,
                          same_slot_average_volume=baseline, settings=settings)
        latest = bars[-1]
        candle = {}
        for field in ("open", "high", "low", "close", "volume"):
            try:
                value = float(latest[field])
            except (KeyError, TypeError, ValueError):
                continue
            if isfinite(value):
                candle[field] = round(value, 4)
        analyzed.append({"symbol": symbol, "candle_time": latest["timestamp"].isoformat(),
                         "candle": candle,
                         "relative_volume": round(rvol, 3),
                         "volume_tier": "STRONG" if rvol >= 2.0 else "QUALIFIED",
                         "signal": result["signal"], "reason": result["reason"],
                         "details": result})
    return {"mode": "PAPER", "universe_count": len(stock_bars),
            "selected_count": len(selected),
            "strong_volume_count": sum(1 for row in analyzed if row["volume_tier"] == "STRONG"),
            "selected": analyzed,
            "excluded": excluded, "min_rvol": min_rvol}
