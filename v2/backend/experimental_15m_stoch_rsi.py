"""Experimental 15-minute Stoch RSI research signals. Never places orders.

Input bars must be completed, contiguous 15-minute candles with timestamp
representing candle START, and a verified 20-session same-slot volume baseline.
This module is intentionally NOT connected to production BUY/SELL decisions.
"""
from dataclasses import dataclass
from datetime import timedelta
from math import isfinite


@dataclass(frozen=True)
class Settings:
    rsi_period: int = 14
    stoch_period: int = 14
    k_smooth: int = 3
    d_smooth: int = 3
    oversold: float = 20.0
    overbought: float = 80.0
    ema_fast: int = 20
    ema_slow: int = 50
    min_rvol: float = 1.5
    min_body_fraction: float = 0.5
    close_edge_fraction: float = 0.25
    breakout_bars: int = 3
    max_age_minutes: int = 18


def _ema(values, period):
    if len(values) < period:
        return []
    alpha = 2 / (period + 1)
    out = [sum(values[:period]) / period]
    for value in values[period:]:
        out.append(alpha * value + (1 - alpha) * out[-1])
    return out


def _rsi(values, period):
    if len(values) <= period:
        return []
    changes = [values[i] - values[i - 1] for i in range(1, len(values))]
    gains = [max(0.0, v) for v in changes]
    losses = [max(0.0, -v) for v in changes]
    gain = sum(gains[:period]) / period
    loss = sum(losses[:period]) / period
    result = []
    for i in range(period - 1, len(changes)):
        if i >= period:
            gain = (gain * (period - 1) + gains[i]) / period
            loss = (loss * (period - 1) + losses[i]) / period
        result.append(50.0 if gain == 0 and loss == 0 else
                      100.0 if loss == 0 else 100 - 100 / (1 + gain / loss))
    return result


def _sma(values, period):
    return [sum(values[i - period + 1:i + 1]) / period
            for i in range(period - 1, len(values))]


def _stoch_rsi(closes, settings):
    rsi = _rsi(closes, settings.rsi_period)
    raw = []
    for i in range(settings.stoch_period - 1, len(rsi)):
        window = rsi[i - settings.stoch_period + 1:i + 1]
        low, high = min(window), max(window)
        raw.append(50.0 if high == low else 100 * (rsi[i] - low) / (high - low))
    k = _sma(raw, settings.k_smooth)
    d = _sma(k, settings.d_smooth)
    return k, d


def evaluate(bars, *, now, same_slot_average_volume, settings=Settings()):
    """Return PAPER_BUY/PAPER_SELL/WAIT with reasons; no execution side effects."""
    def wait(reason):
        return {"signal": "WAIT", "mode": "PAPER", "reason": reason}
    required = max(settings.ema_slow + 2,
                   settings.rsi_period + settings.stoch_period +
                   settings.k_smooth + settings.d_smooth + 2,
                   settings.breakout_bars + 1)
    if len(bars) < required:
        return wait("INSUFFICIENT_15M_HISTORY")
    recent = bars[-required:]
    # Indicators span sessions; overnight gaps are expected, intraday gaps are not.
    for earlier, later in zip(recent, recent[1:]):
        delta = later["timestamp"] - earlier["timestamp"]
        if delta != timedelta(minutes=15):
            if earlier["timestamp"].date() == later["timestamp"].date():
                return wait("NONCONTIGUOUS_15M_CANDLES")
            if delta <= timedelta(0):
                return wait("UNSORTED_15M_HISTORY")
    if any(bar["timestamp"].date() != recent[-1]["timestamp"].date()
           for bar in recent[-settings.breakout_bars - 1:]):
        return wait("INSUFFICIENT_SAME_SESSION_BREAKOUT_BARS")
    latest = recent[-1]
    age = (now - (latest["timestamp"] + timedelta(minutes=15))).total_seconds() / 60
    if age < 0 or age > settings.max_age_minutes:
        return wait("STALE_OR_INCOMPLETE_15M_CANDLE")
    if (not isinstance(same_slot_average_volume, (int, float)) or not isfinite(same_slot_average_volume) or same_slot_average_volume <= 0):
        return wait("MISSING_VERIFIED_20_SESSION_VOLUME_BASELINE")
    try:
        values = [float(bar["close"]) for bar in recent]
        if not all(isfinite(x) and x > 0 for x in values):
            return wait("INVALID_PRICE")
        high, low, opn, close = (float(latest[key]) for key in ("high", "low", "open", "close"))
        volume = float(latest["volume"])
    except (KeyError, TypeError, ValueError):
        return wait("INVALID_CANDLE")
    if not all(isfinite(x) for x in (high, low, opn, close, volume)) or high <= low or volume < 0:
        return wait("INVALID_CANDLE")
    rvol = volume / same_slot_average_volume
    if rvol < settings.min_rvol:
        return wait("VOLUME_BELOW_THRESHOLD")
    body = abs(close - opn) / (high - low)
    if body < settings.min_body_fraction:
        return wait("WEAK_CANDLE_BODY")
    fast, slow = _ema(values, settings.ema_fast), _ema(values, settings.ema_slow)
    k, d = _stoch_rsi(values, settings)
    if len(k) < 2 or len(d) < 2:
        return wait("INSUFFICIENT_STOCH_RSI_HISTORY")
    # k and d arrays have different starting offsets, but their last two
    # observations refer to the same two most recent completed candles.
    bullish_cross = (k[-2] <= d[-2] and k[-1] > d[-1]
                     and k[-1] <= settings.oversold)
    bearish_cross = (k[-2] >= d[-2] and k[-1] < d[-1]
                     and k[-1] >= settings.overbought)
    prior = recent[-settings.breakout_bars - 1:-1]
    buy = (fast[-1] > slow[-1] and close > opn and
           close >= high - settings.close_edge_fraction * (high - low) and
           close > max(bar["high"] for bar in prior) and bullish_cross)
    sell = (fast[-1] < slow[-1] and close < opn and
            close <= low + settings.close_edge_fraction * (high - low) and
            close < min(bar["low"] for bar in prior) and bearish_cross)
    signal = "PAPER_BUY" if buy else "PAPER_SELL" if sell else "WAIT"
    ema20, ema50 = fast[-1], slow[-1]
    trend = "BULLISH" if ema20 > ema50 else "BEARISH" if ema20 < ema50 else "NEUTRAL"
    return {"signal": signal, "mode": "PAPER", "rvol": round(rvol, 3),
            "stoch_k": round(k[-1], 2), "stoch_d": round(d[-1], 2),
            "ema20": round(ema20, 4), "ema50": round(ema50, 4), "trend": trend,
            "targets_pct": [0.3, 0.5, 0.75, 1.0] if buy or sell else [],
            "reason": "15M_FILTERS_PASSED" if buy or sell else "NO_QUALIFYING_SETUP"}
