def generate_signal(price, ema9, ema20, vwap, momentum, rvol=None, market=None):
    # Core price indicators are mandatory.
    if None in (price, ema9, ema20, momentum):
        return "WATCH"

    # Require relative-volume confirmation in both directions when available.
    # Index feeds may not provide traded volume; stock callers supply RVOL.
    volume_ok = True if rvol is None else rvol >= 1

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

    # NIFTY market regime is informational; stock BUY is decided by stock-specific rules.
    if bullish:
        return "BUY"

    if bearish:
        return "SELL"

    return "HOLD"


print("V2_SIGNAL_RULES_OK")
