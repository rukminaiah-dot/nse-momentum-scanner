def generate_signal(price, ema9, ema20, vwap, momentum, rvol=None, market=None):
    # Core price indicators are mandatory.
    if None in (price, ema9, ema20, momentum):
        return "WATCH"

    # Stock callers must provide verified VWAP and RVOL to qualify for BUY.
    # Index callers may lack volume and use their separate index signal logic.
    volume_ok = rvol is not None and rvol >= 1

    bullish = (
        vwap is not None
        and price > vwap
        and ema9 > ema20
        and momentum > 0
        and volume_ok
    )

    bearish = (
        (vwap is None or price < vwap)
        and ema9 < ema20
        and momentum < 0
    )

    # NIFTY market regime is informational; stock BUY is decided by stock-specific rules.
    if bullish:
        return "BUY"

    if bearish:
        return "SELL"

    return "HOLD"


print("V2_SIGNAL_RULES_OK")
