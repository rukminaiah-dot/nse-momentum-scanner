"""Conservative validation and breakout calculations for completed NSE daily candles.

This module makes no network requests and never places orders.
Input: chronological list of dictionaries with date, open, high, low, close, volume.
"""
from datetime import date, datetime
from math import isfinite

class DataRejected(ValueError):
    pass

def evaluate(symbol, candles, as_of=None, capital=500000, max_risk=2500):
    """Return either a verified setup or a reason for no signal."""
    try:
        if not isinstance(candles, list) or len(candles) < 70:
            raise DataRejected("INSUFFICIENT_HISTORY_70_CANDLES")
        parsed = []
        seen = set()
        for row in candles:
            day = date.fromisoformat(str(row["date"])[:10])
            if day in seen:
                raise DataRejected("DUPLICATE_SESSION")
            seen.add(day)
            o, h, l, c, v = (float(row[k]) for k in ("open", "high", "low", "close", "volume"))
            if not all(isfinite(x) for x in (o, h, l, c, v)) or min(o, h, l, c) <= 0 or v <= 0:
                raise DataRejected("INVALID_PRICE_OR_VOLUME")
            if l > min(o, c) or h < max(o, c) or l > h:
                raise DataRejected("INCONSISTENT_OHLC")
            parsed.append((day, o, h, l, c, v))
        if parsed != sorted(parsed):
            raise DataRejected("NON_CHRONOLOGICAL_HISTORY")
        today = as_of or date.today()
        if isinstance(today, str):
            today = date.fromisoformat(today)
        if parsed[-1][0] > today:
            raise DataRejected("FUTURE_DATED_CANDLE")
        if (today - parsed[-1][0]).days > 5:
            raise DataRejected("STALE_HISTORY")
        close = [x[4] for x in parsed]
        volume = [x[5] for x in parsed]
        gains = [max(close[i] - close[i-1], 0) for i in range(1, len(close))]
        losses = [max(close[i-1] - close[i], 0) for i in range(1, len(close))]
        avg_gain = sum(gains[:14]) / 14
        avg_loss = sum(losses[:14]) / 14
        for g, l in zip(gains[14:], losses[14:]):
            avg_gain = (avg_gain * 13 + g) / 14
            avg_loss = (avg_loss * 13 + l) / 14
        rsi = 100 if avg_loss == 0 else 100 - 100 / (1 + avg_gain / avg_loss)
        last = close[-1]
        previous_20_high = max(x[2] for x in parsed[-21:-1])
        previous_55_high = max(x[2] for x in parsed[-56:-1])
        ma20 = sum(close[-20:]) / 20
        ma50 = sum(close[-50:]) / 50
        avg_volume20 = sum(volume[-21:-1]) / 20
        checks = {
            "breakout_20d": last > previous_20_high,
            "breakout_55d": last > previous_55_high,
            "volume_1_5x": volume[-1] >= 1.5 * avg_volume20,
            "above_ma20_ma50": last > ma20 and last > ma50,
            "rsi_50_to_75": 50 <= rsi <= 75,
        }
        result = {"symbol": symbol, "status": "NO_SIGNAL", "session": parsed[-1][0].isoformat(),
                  "checks": checks, "rsi14": round(rsi, 2), "entry": None,
                  "stop": None, "target_2r": None, "target_3r": None, "quantity": 0}
        if not all(checks.values()):
            return result
        support = min(x[3] for x in parsed[-11:-1])
        risk = last - support
        if risk <= 0 or risk / last > 0.06 or risk / last < 0.01:
            result["status"] = "REJECTED_STOP_DISTANCE"
            return result
        quantity = min(int(max_risk // risk), int(capital // last))
        if quantity < 1:
            result["status"] = "REJECTED_POSITION_SIZE"
            return result
        result.update(status="TECHNICAL_SETUP_REQUIRES_REVIEW", entry=round(last, 2),
                      stop=round(support, 2), target_2r=round(last + 2 * risk, 2),
                      target_3r=round(last + 3 * risk, 2), quantity=quantity,
                      planned_risk=round(quantity * risk, 2),
                      required_capital=round(quantity * last, 2))
        return result
    except (DataRejected, KeyError, TypeError, ValueError, OverflowError) as exc:
        return {"symbol": symbol, "status": "DATA_UNVERIFIED",
                "reason": str(exc) if isinstance(exc, DataRejected) else "MALFORMED_CANDLE_DATA",
                "entry": None, "stop": None, "target_2r": None, "target_3r": None, "quantity": 0}
