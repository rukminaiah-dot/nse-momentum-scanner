import yfinance as yf
from backend.symbols import SYMBOLS


def signals():
    data = yf.download(SYMBOLS, period="5d", interval="15m", progress=False, group_by="column")
    results = []
    if data.empty:
        return results

    close = data["Close"].ffill()
    volume = data["Volume"].fillna(0)
    low = data["Low"].ffill()

    for ticker in SYMBOLS:
        try:
            c = close[ticker].dropna()
            v = volume[ticker].dropna()
            lo = low[ticker].dropna()
            if len(c) < 21 or len(v) < 21:
                continue

            price = float(c.iloc[-1])
            momentum = float((c.iloc[-1] / c.iloc[-2] - 1) * 100)
            avg_volume = float(v.iloc[-21:-1].mean())
            relative_volume = float(v.iloc[-1] / avg_volume) if avg_volume > 0 else 0.0
            ema20 = float(c.ewm(span=20, adjust=False).mean().iloc[-1])
            invalidation = float(lo.tail(5).min())

            if momentum > 0 and relative_volume >= 1.2 and price > ema20:
                results.append({"ticker": ticker, "price": round(price, 2), "momentum_pct": round(momentum, 2), "relative_volume": round(relative_volume, 2), "trend": "above_ema20", "invalidation": round(invalidation, 2)})
        except (KeyError, IndexError, TypeError, ValueError):
            continue

    return sorted(results, key=lambda x: (x["relative_volume"], x["momentum_pct"]), reverse=True)
