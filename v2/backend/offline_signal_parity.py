"""Pure, offline scanner decision model. Does not import the live scanner.

This is an independent parity candidate, not wired into production.
"""
from datetime import timedelta
from v2.backend.indicators import ema, momentum, atr
from v2.backend.signal_engine import generate_signal
from v2.backend.market_regime import index_signal
from v2.backend.volume_metrics import (
    completed_intraday_bars, verified_same_slot_relative_volume,
    confirmed_range_breakout,
)
from v2.backend.stock_setup_rules import SetupConfig, evaluate_stock_setup


def five_minute_trend(history):
    timed = [c for c in history if hasattr(c, "timestamp")]
    if timed:
        day = timed[-1].timestamp.date()
        timed = [c for c in timed if c.timestamp.date() == day]
    if len(timed) < 15:
        return "NEUTRAL"
    buckets = {}
    for candle in timed:
        ts = candle.timestamp
        bucket = ts.replace(minute=(ts.minute // 5) * 5, second=0, microsecond=0)
        buckets.setdefault(bucket, []).append(candle)
    complete = []
    for key in sorted(buckets):
        group = buckets[key]
        if len(group) == 5 and all(
                (group[i].timestamp - group[i-1].timestamp).total_seconds() == 60
                for i in range(1, 5)):
            complete.append(group)
    if len(complete) < 3:
        return "NEUTRAL"
    latest_groups = complete[-3:]
    if any((latest_groups[i][0].timestamp -
            latest_groups[i-1][0].timestamp).total_seconds() != 300
           for i in range(1, 3)):
        return "NEUTRAL"
    closes = [group[-1].close for group in latest_groups]
    if closes[0] < closes[1] < closes[2]:
        return "BULLISH"
    if closes[0] > closes[1] > closes[2]:
        return "BEARISH"
    return "NEUTRAL"



def five_minute_breakout(history, direction):
    """Confirm a completed 5-minute close beyond the prior 15-minute range."""
    timed = [c for c in history if hasattr(c, "timestamp")]
    if not timed:
        return False
    day = timed[-1].timestamp.date()
    timed = [c for c in timed if c.timestamp.date() == day]
    buckets = {}
    for candle in timed:
        ts = candle.timestamp
        bucket = ts.replace(minute=(ts.minute // 5) * 5, second=0, microsecond=0)
        buckets.setdefault(bucket, []).append(candle)
    complete = []
    for key in sorted(buckets):
        group = buckets[key]
        if len(group) == 5 and all(
                (group[i].timestamp - group[i-1].timestamp).total_seconds() == 60
                for i in range(1, 5)):
            complete.append(group)
    if len(complete) < 4:
        return False
    last_four = complete[-4:]
    if any((last_four[i][0].timestamp -
            last_four[i-1][0].timestamp).total_seconds() != 300
           for i in range(1, 4)):
        return False
    prior = last_four[:3]
    prior_high = max(float(c.high) for group in prior for c in group)
    prior_low = min(float(c.low) for group in prior for c in group)
    prior_ranges = [
        max(float(c.high) for c in group) - min(float(c.low) for c in group)
        for group in prior
    ]
    latest_close = float(last_four[-1][-1].close)
    if latest_close <= 0:
        return False
    buffer = max(latest_close * 0.001,
                 0.25 * (sum(prior_ranges) / len(prior_ranges)))
    if direction == "BUY":
        return latest_close > prior_high + buffer
    if direction == "SELL":
        return latest_close < prior_low - buffer
    return False

def evaluate(history, *, session_date, is_index=False, is_stock=False,
             nifty_market="NEUTRAL", is_primary_index=True,
             historical_15m_rows=(), historical_5m_rows=(), levels=None,
             now=None, previous_state=None):
    """Pure offline decision model. Stock setups require verified levels/RVOL."""
    if is_index and is_stock:
        raise ValueError("instrument cannot be both index and stock")
    if len(history) < 20:
        return {"signal": "BLOCKED", "reason": "WARMUP"}
    if is_index:
        history = [c for c in history if hasattr(c, "timestamp")
                   and c.timestamp.date() == session_date]
        if len(history) < 20:
            return {"signal": "BLOCKED", "reason": "WARMUP"}
    recent = history[-6:]
    if len(recent) < 6:
        reason = "WARMUP"
    elif any(not hasattr(c, "timestamp") or c.timestamp.date() != session_date
             for c in recent):
        reason = "OVERNIGHT_GAP"
    elif any(recent[i].timestamp - recent[i-1].timestamp != timedelta(minutes=1)
             for i in range(1, 6)):
        reason = "MISSING_MINUTE"
    else:
        reason = None
    if reason:
        return {"signal": "BLOCKED", "reason": reason}
    closes = [c.close for c in history]
    highs = [c.high for c in history]
    lows = [c.low for c in history]
    price = closes[-1]
    e9, e20 = ema(closes, 9), ema(closes, 20)
    mom = momentum(closes)
    atr14 = atr(highs, lows, closes, 14)
    market = (index_signal(price, e9, e20, None)
              if is_index and is_primary_index else nifty_market)
    trend = five_minute_trend(history)
    if is_stock:
        bars_5m = completed_intraday_bars(history, 5)
        if now is None:
            now = bars_5m[-1]["timestamp"] + timedelta(minutes=5) if bars_5m else history[-1].timestamp
        setup = evaluate_stock_setup(
            "OFFLINE", bars_5m, historical_5m_rows or historical_15m_rows,
            levels or {}, now=now, ema9=e9, ema20=e20,
            previous_state=previous_state, config=SetupConfig(),
        )
        signal = ("BUY" if setup["status"] == "CONFIRMED" and setup["direction"] == "LONG"
                  else "SELL" if setup["status"] == "CONFIRMED" and setup["direction"] == "SHORT"
                  else "HOLD")
        return {"signal": signal, "reason": None, "setup": setup,
                "ema9": e9, "ema20": e20, "momentum": mom, "atr14": atr14,
                "rvol": setup.get("relative_volume"), "current_volume": None,
                "baseline_volume": setup.get("relative_volume_baseline"),
                "trend_5m": trend, "market": market}
    signal = generate_signal(price, e9, e20, None, mom, None, market,
                             require_volume=False)
    if signal in ("BUY", "SELL"):
        expected_trend = "BULLISH" if signal == "BUY" else "BEARISH"
        if trend != expected_trend or not five_minute_breakout(history, signal):
            signal = "HOLD"
    return {"signal": signal, "reason": None, "ema9": e9, "ema20": e20,
            "momentum": mom, "atr14": atr14, "rvol": None,
            "current_volume": None, "baseline_volume": None,
            "trend_5m": trend, "market": market}
