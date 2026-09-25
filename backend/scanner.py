import yfinance as yf
import pandas as pd

SYMBOLS = [
    "RELIANCE.NS",
    "TCS.NS",
    "HDFCBANK.NS",
    "ICICIBANK.NS",
    "INFY.NS",
    "SBIN.NS",
    "BHARTIARTL.NS",
    "ITC.NS",
    "LT.NS",
    "AXISBANK.NS",
]


def signals():
    try:
        data = yf.download(
            SYMBOLS,
            period="5d",
            interval="15m",
            group_by="column",
            auto_adjust=True,
            progress=False,
            threads=True,
        )

        if data.empty:
            return []

        results = []

        for ticker in SYMBOLS:
            try:
                close = data["Close"][ticker].dropna()
                volume = data["Volume"][ticker].dropna()

                if len(close) < 20 or len(volume) < 20:
                    continue

                price = float(close.iloc[-1])
                previous = float(close.iloc[-2])

                change_pct = (
                    ((price - previous) / previous) * 100
                    if previous
                    else 0
                )

                avg_volume = float(volume.tail(20).mean())
                current_volume = float(volume.iloc[-1])

                relative_volume = (
                    current_volume / avg_volume
                    if avg_volume > 0
                    else 0
                )

                ema9 = close.ewm(span=9, adjust=False).mean()
                ema20 = close.ewm(span=20, adjust=False).mean()

                bullish_trend = (
                    price > float(ema9.iloc[-1])
                    and price > float(ema20.iloc[-1])
                )

                recent_low = float(close.tail(10).min())

                # Only show stronger observed momentum.
                if change_pct <= 0:
                    continue

                if relative_volume < 0.80:
                    continue

                if not bullish_trend:
                    continue

                score = min(
                    100,
                    round(
                        50
                        + min(relative_volume, 3) * 12
                        + min(change_pct, 2) * 10
                    ),
                )

                results.append(
                    {
                        "ticker": ticker,
                        "price": round(price, 2),
                        "momentum_pct": round(change_pct, 2),
                        "relative_volume": round(relative_volume, 2),
                        "trend": "Bullish",
                        "score": score,
                        "reason": (
                            f"Positive 15m momentum • "
                            f"RVOL {relative_volume:.2f}x • "
                            f"price above EMA9 and EMA20"
                        ),
                        "invalidation": round(recent_low, 2),
                    }
                )

            except Exception:
                continue

        results.sort(
            key=lambda item: item["score"],
            reverse=True,
        )

        return results

    except Exception as exc:
        print("Scanner error:", exc)
        return []
