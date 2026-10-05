def generate_signal(price, ema9, ema20, vwap, momentum, rvol=None, market=None):
    # Core price indicators are mandatory.
    if None in (price, ema9, ema20, momentum):
        return "WATCH"

    # Volume is optional.
    # Index feeds such as Nifty/Sensex may not provide traded volume.
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
    )

    if bullish and market != "BEARISH":
        return "BUY"

    if bearish:
        return "SELL"

    return "HOLD"


print("V2_SIGNAL_RULES_OK")
