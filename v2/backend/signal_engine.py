"""Conservative research signal filter for completed candles.

Thresholds reduce marginal one-minute flips. They are heuristic and have not
been validated for profitability; this module never places broker orders.
"""


def generate_signal(price, ema9, ema20, vwap, momentum, rvol=None, market=None,
                    *, require_volume=False, min_relative_volume=1.5,
                    min_ema_spread_pct=0.10):
    # Core price indicators are mandatory.
    if None in (price, ema9, ema20, momentum):
        return "WATCH"

    try:
        price = float(price)
        ema9 = float(ema9)
        ema20 = float(ema20)
        momentum = float(momentum)
        spread_floor = float(min_ema_spread_pct)
        volume_floor = float(min_relative_volume)
    except (TypeError, ValueError, OverflowError):
        return "HOLD"

    if price <= 0:
        return "HOLD"

    # Require a wider EMA gap; smaller separations are treated as crossover noise.
    spread_pct = abs(ema9 - ema20) / price * 100
    if spread_pct < spread_floor:
        return "HOLD"

    # Stocks require verified observed volume. Missing RVOL is not treated as
    # confirmation, and merely average volume is filtered out.
    if require_volume:
        if rvol is None:
            return "HOLD"
        try:
            rvol = float(rvol)
        except (TypeError, ValueError, OverflowError):
            return "HOLD"
        if rvol < volume_floor:
            return "HOLD"

    if rvol is not None and not require_volume:
        try:
            if float(rvol) < volume_floor:
                return "HOLD"
        except (TypeError, ValueError, OverflowError):
            return "HOLD"

    volume_ok = True
    bullish = (
        (vwap is None or price > vwap)
        and ema9 > ema20
        and momentum > 0
        and volume_ok
    )
    bearish = (
        (vwap is None or price < vwap)
        and ema9 < ema20
        and momentum < 0
        and volume_ok
    )
    if bullish:
        return "BUY"
    if bearish:
        return "SELL"
    return "HOLD"
