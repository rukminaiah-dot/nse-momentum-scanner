"""Pure research-only trend confirmation from completed one-minute index candles.

This module never connects to a broker, places orders or recommends contracts.
"""
from dataclasses import dataclass
from datetime import datetime, timedelta, time
from math import isfinite
from zoneinfo import ZoneInfo

IST = ZoneInfo("Asia/Kolkata")


@dataclass(frozen=True)
class TrendConfirmation:
    direction: str
    status: str
    reason: str
    candle_ist: str | None
    last_close: float | None
    ema_fast: float | None
    ema_slow: float | None


def _ema(values, period):
    alpha = 2 / (period + 1)
    result = values[0]
    for value in values[1:]:
        result = alpha * value + (1 - alpha) * result
    return result


def confirm_index_trend(candles, *, now=None):
    """Confirm direction only from ordered, completed 1m candles.

    Each candle is a (datetime, close) tuple. Timestamps are naive IST or
    timezone-aware; future, duplicate, unordered, stale and cross-day inputs
    fail closed. Requires at least 30 completed candles.
    """
    now = now or datetime.now(IST)
    if now.tzinfo is None:
        raise ValueError("now must be timezone-aware")
    now = now.astimezone(IST)
    empty = TrendConfirmation("NONE", "WAIT", "INSUFFICIENT_CANDLES", None, None, None, None)
    if len(candles) < 30:
        return empty
    parsed = []
    for stamp, close in candles:
        if not isinstance(stamp, datetime):
            return TrendConfirmation("NONE", "WAIT", "INVALID_CANDLE", None, None, None, None)
        stamp = stamp.replace(tzinfo=IST) if stamp.tzinfo is None else stamp.astimezone(IST)
        try:
            price = float(close)
        except (TypeError, ValueError, OverflowError):
            return TrendConfirmation("NONE", "WAIT", "INVALID_PRICE", None, None, None, None)
        if not isfinite(price) or price <= 0:
            return TrendConfirmation("NONE", "WAIT", "INVALID_PRICE", None, None, None, None)
        parsed.append((stamp, price))
    if any(parsed[i][0] >= parsed[i + 1][0] for i in range(len(parsed) - 1)):
        return TrendConfirmation("NONE", "WAIT", "UNORDERED_CANDLES", None, None, None, None)
    last = parsed[-1][0]
    label = last.strftime("%Y-%m-%d %H:%M:%S")
    closes = [price for _, price in parsed]
    fast, slow = _ema(closes, 9), _ema(closes, 20)
    base = TrendConfirmation("NONE", "WAIT", "UNCONFIRMED", label, closes[-1], fast, slow)
    if any(stamp.date() != now.date() for stamp, _ in parsed[-30:]):
        return TrendConfirmation("NONE", "WAIT", "CROSS_SESSION_CANDLES", label, closes[-1], fast, slow)
    if not (time(9, 15) <= last.time() <= time(15, 30)):
        return TrendConfirmation("NONE", "WAIT", "OUTSIDE_MARKET_SESSION", label, closes[-1], fast, slow)
    age = now - last
    if not (timedelta(0) <= age <= timedelta(minutes=3)):
        return TrendConfirmation("NONE", "WAIT", "STALE_OR_FUTURE_CANDLE", label, closes[-1], fast, slow)
    if now.weekday() >= 5:
        return TrendConfirmation("NONE", "WAIT", "MARKET_CLOSED", label, closes[-1], fast, slow)
    last_three = closes[-3:]
    if fast > slow and last_three[0] < last_three[1] < last_three[2] and closes[-1] > fast:
        return TrendConfirmation("BULLISH", "CONFIRMED_RESEARCH_ONLY", "EMA_AND_RISING_CLOSES", label, closes[-1], fast, slow)
    if fast < slow and last_three[0] > last_three[1] > last_three[2] and closes[-1] < fast:
        return TrendConfirmation("BEARISH", "CONFIRMED_RESEARCH_ONLY", "EMA_AND_FALLING_CLOSES", label, closes[-1], fast, slow)
    return base
