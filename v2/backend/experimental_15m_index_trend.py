"""Read-only 15-minute index trend shifts for the experimental paper dashboard.

Spot indices have no verified tradable volume baseline. This evaluator uses
completed Upstox 15-minute OHLC candles, 21 prior sessions of history, EMA20/50,
and Stochastic RSI (14, 14, 3, 3). Signals are paper labels only.
"""
from __future__ import annotations

import os
from datetime import datetime, timedelta
from math import isfinite
from zoneinfo import ZoneInfo

IST = ZoneInfo("Asia/Kolkata")
INDEX_INSTRUMENTS = {
    "NIFTY 50": "NSE_INDEX|Nifty 50",
    "SENSEX": "BSE_INDEX|SENSEX",
    "BANK NIFTY": "NSE_INDEX|Nifty Bank",
}
REQUIRED_PRIOR_SESSIONS = 21
RSI_PERIOD = 14
STOCH_PERIOD = 14
K_SMOOTH = 3
D_SMOOTH = 3


def _parse_rows(rows):
    bars = []
    for row in rows or ():
        try:
            stamp = datetime.fromisoformat(str(row[0]).replace("Z", "+00:00"))
            if stamp.tzinfo is None:
                continue
            stamp = stamp.astimezone(IST).replace(tzinfo=None)
            values = [float(value) for value in row[1:5]]
            if len(values) != 4 or not all(isfinite(value) and value > 0 for value in values):
                continue
            opn, high, low, close = values
            if high < max(opn, close, low) or low > min(opn, close, high) or high <= low:
                continue
            bars.append({"timestamp": stamp, "open": opn, "high": high,
                         "low": low, "close": close})
        except (IndexError, TypeError, ValueError, AttributeError, OverflowError):
            continue
    return sorted(bars, key=lambda bar: bar["timestamp"])


def _ema(values, period):
    if len(values) < period:
        return []
    alpha = 2 / (period + 1)
    result = [sum(values[:period]) / period]
    for value in values[period:]:
        result.append(alpha * value + (1 - alpha) * result[-1])
    return result


def _rsi(values, period=RSI_PERIOD):
    if len(values) <= period:
        return []
    changes = [values[i] - values[i - 1] for i in range(1, len(values))]
    gains = [max(0.0, value) for value in changes]
    losses = [max(0.0, -value) for value in changes]
    average_gain = sum(gains[:period]) / period
    average_loss = sum(losses[:period]) / period
    result = []
    for i in range(period - 1, len(changes)):
        if i >= period:
            average_gain = (average_gain * (period - 1) + gains[i]) / period
            average_loss = (average_loss * (period - 1) + losses[i]) / period
        result.append(50.0 if average_gain == average_loss == 0 else
                      100.0 if average_loss == 0 else
                      100 - 100 / (1 + average_gain / average_loss))
    return result


def _sma(values, period):
    return [sum(values[i - period + 1:i + 1]) / period
            for i in range(period - 1, len(values))]


def _stoch_rsi(values):
    rsi = _rsi(values)
    raw = []
    for i in range(STOCH_PERIOD - 1, len(rsi)):
        window = rsi[i - STOCH_PERIOD + 1:i + 1]
        low, high = min(window), max(window)
        raw.append(50.0 if high == low else 100 * (rsi[i] - low) / (high - low))
    k = _sma(raw, K_SMOOTH)
    d = _sma(k, D_SMOOTH)
    return k, d


def evaluate_index(symbol, bars, *, now, min_prior_sessions=REQUIRED_PRIOR_SESSIONS):
    """Return a paper-only 15m signal and explainable quality/indicator fields."""
    def wait(reason, **extra):
        return {"symbol": symbol, "mode": "PAPER", "signal": "WAIT",
                "data_status": "UNAVAILABLE", "reason": reason, **extra}

    if now.tzinfo is None:
        raise ValueError("now must be timezone-aware")
    now = now.astimezone(IST)
    if not isinstance(min_prior_sessions, int) or min_prior_sessions < 21:
        raise ValueError("min_prior_sessions must be at least 21")
    if not bars:
        return wait("NO_15M_CANDLES")
    ordered = sorted(bars, key=lambda bar: bar.get("timestamp", datetime.min))
    stamps = [bar.get("timestamp") for bar in ordered]
    if any(not isinstance(stamp, datetime) for stamp in stamps):
        return wait("INVALID_CANDLE_TIMESTAMP")
    if len(stamps) != len(set(stamps)):
        return wait("DUPLICATE_15M_CANDLES")
    for earlier, later in zip(ordered, ordered[1:]):
        delta = later["timestamp"] - earlier["timestamp"]
        if delta <= timedelta(0):
            return wait("UNSORTED_15M_HISTORY")
        if earlier["timestamp"].date() == later["timestamp"].date() and delta != timedelta(minutes=15):
            return wait("NONCONTIGUOUS_15M_CANDLES")
    today = now.date()
    prior_sessions = {bar["timestamp"].date() for bar in ordered
                      if bar["timestamp"].date() < today}
    if len(prior_sessions) < min_prior_sessions:
        return wait("INSUFFICIENT_21_PRIOR_SESSIONS",
                    prior_session_count=len(prior_sessions),
                    required_prior_sessions=min_prior_sessions)
    session = [bar for bar in ordered
               if bar["timestamp"].date() == today
               and 9 * 60 + 15 <= bar["timestamp"].hour * 60 + bar["timestamp"].minute <= 15 * 60 + 15
               and (bar["timestamp"].hour * 60 + bar["timestamp"].minute - 555) % 15 == 0
               and bar["timestamp"] + timedelta(minutes=15) <= now.replace(tzinfo=None)]
    if not session:
        return wait("NO_COMPLETED_CURRENT_SESSION_CANDLE",
                    prior_session_count=len(prior_sessions))
    latest = session[-1]
    if now.replace(tzinfo=None) - (latest["timestamp"] + timedelta(minutes=15)) > timedelta(minutes=18):
        return wait("STALE_15M_CANDLE", prior_session_count=len(prior_sessions))
    closes = [bar["close"] for bar in ordered
              if bar["timestamp"] + timedelta(minutes=15) <= now.replace(tzinfo=None)]
    if len(closes) < 52:
        return wait("INSUFFICIENT_INDICATOR_HISTORY",
                    prior_session_count=len(prior_sessions))
    recent = session[-4:]
    if len(recent) < 4:
        return wait("INSUFFICIENT_SAME_SESSION_BREAKOUT_BARS",
                    prior_session_count=len(prior_sessions))
    try:
        opn, high, low, close = (float(latest[key]) for key in ("open", "high", "low", "close"))
        if not all(isfinite(value) and value > 0 for value in (opn, high, low, close)) or high <= low:
            return wait("INVALID_CANDLE", prior_session_count=len(prior_sessions))
    except (KeyError, TypeError, ValueError, OverflowError):
        return wait("INVALID_CANDLE", prior_session_count=len(prior_sessions))
    fast, slow = _ema(closes, 20), _ema(closes, 50)
    k, d = _stoch_rsi(closes)
    if len(k) < 2 or len(d) < 2 or not fast or not slow:
        return wait("INSUFFICIENT_INDICATOR_HISTORY",
                    prior_session_count=len(prior_sessions))
    body = abs(close - opn) / (high - low)
    bullish_cross = k[-2] <= d[-2] and k[-1] > d[-1] and k[-1] <= 20
    bearish_cross = k[-2] >= d[-2] and k[-1] < d[-1] and k[-1] >= 80
    prior = recent[-4:-1]
    buy = (fast[-1] > slow[-1] and bullish_cross and close > opn
           and body >= 0.5 and close >= high - 0.25 * (high - low)
           and close > max(bar["high"] for bar in prior))
    sell = (fast[-1] < slow[-1] and bearish_cross and close < opn
            and body >= 0.5 and close <= low + 0.25 * (high - low)
            and close < min(bar["low"] for bar in prior))
    signal = "PAPER_BUY" if buy else "PAPER_SELL" if sell else "WAIT"
    return {
        "symbol": symbol, "mode": "PAPER", "signal": signal,
        "data_status": "LIVE_FRESH", "last_candle_ist": latest["timestamp"].isoformat(),
        "prior_session_count": len(prior_sessions), "ema20": round(fast[-1], 2),
        "ema50": round(slow[-1], 2), "stoch_k": round(k[-1], 2),
        "stoch_d": round(d[-1], 2), "rvol": None,
        "reason": "STOCH_RSI_CROSS_AND_TREND_FILTERS_PASSED" if signal != "WAIT"
                  else "NO_QUALIFYING_15M_SHIFT",
    }


def run(*, now=None, api=None, lookback_days=90):
    """Fetch read-only 15m index history and intraday data from Upstox V3."""
    now = now or datetime.now(IST)
    if now.tzinfo is None:
        raise ValueError("now must be timezone-aware")
    now = now.astimezone(IST)
    if api is None:
        import upstox_client
        configuration = upstox_client.Configuration()
        configuration.access_token = os.environ["UPSTOX_ACCESS_TOKEN"]
        api = upstox_client.HistoryV3Api(upstox_client.ApiClient(configuration))
    to_date = (now.date() - timedelta(days=1)).isoformat()
    from_date = (now.date() - timedelta(days=lookback_days + 1)).isoformat()
    results, errors = [], {}
    for symbol, key in INDEX_INSTRUMENTS.items():
        try:
            historical = api.get_historical_candle_data1(
                key, "minutes", "15", to_date, from_date)
            history = _parse_rows(historical.data.candles or [])
            intraday = api.get_intra_day_candle_data(key, "minutes", "15")
            current = _parse_rows(intraday.data.candles or [])
            complete = [bar for bar in current
                        if bar["timestamp"].date() == now.date()
                        and bar["timestamp"] + timedelta(minutes=15) <= now.replace(tzinfo=None)]
            results.append(evaluate_index(symbol, history + complete, now=now))
        except Exception as exc:
            errors[symbol] = type(exc).__name__
            results.append({"symbol": symbol, "mode": "PAPER", "signal": "WAIT",
                            "data_status": "UNAVAILABLE", "reason": "UPSTOX_FETCH_FAILED"})
    return {"mode": "PAPER", "source": "UPSTOX_HISTORY_V3",
            "as_of_ist": now.isoformat(), "indices": results, "fetch_errors": errors}
