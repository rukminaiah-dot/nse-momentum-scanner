"""Explainable, intraday index trend-shift monitor based on stored completed candles.

This is a research display only. It reports an early watch separately from a
confirmed indicator shift and never emits orders or profit probabilities.
"""
from __future__ import annotations

import math
import sqlite3
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

from .database import DB_PATH

IST = ZoneInfo("Asia/Kolkata")
INDEX_NAMES = ("NIFTY 50", "SENSEX", "BANK NIFTY")
MAX_CANDLES = 40


def _float(value):
    try:
        number = float(value)
        return number if math.isfinite(number) else None
    except (TypeError, ValueError, OverflowError):
        return None


def _stamp(value):
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value)
        except ValueError:
            return None
    else:
        return None
    return parsed.replace(tzinfo=IST) if parsed.tzinfo is None else parsed.astimezone(IST)


def _stable_direction(row):
    _, price, ema9, ema20, momentum = row
    if None in (price, ema9, ema20, momentum):
        return None
    if ema9 > ema20 and momentum > 0:
        return "BULLISH"
    if ema9 < ema20 and momentum < 0:
        return "BEARISH"
    return None


def _pressure_direction(row):
    _, price, ema9, _ema20, momentum = row
    if None in (price, ema9, momentum):
        return None
    if price > ema9 and momentum > 0:
        return "BULLISH"
    if price < ema9 and momentum < 0:
        return "BEARISH"
    return None


def assess_index_shift(rows, *, now=None):
    """Assess an index from ascending (time, price, EMA9, EMA20, momentum) rows.

    Two consecutive closes with price/momentum on the same side of EMA9 create
    an early watch when the recent EMA trend was opposite. A confirmed research
    shift additionally requires three aligned EMA/momentum rows and three
    strictly directional closes. Freshness is always reported independently.
    """
    now = now or datetime.now(IST)
    if now.tzinfo is None:
        raise ValueError("now must be timezone-aware")
    now = now.astimezone(IST)
    parsed = []
    for stamp, price, ema9, ema20, momentum in rows:
        stamp = _stamp(stamp)
        values = tuple(_float(v) for v in (price, ema9, ema20, momentum))
        if stamp is None or any(v is None for v in values):
            continue
        parsed.append((stamp, *values))
    parsed.sort(key=lambda item: item[0])
    today_rows = [row for row in parsed if row[0].date() == now.date()]
    session_rows = [row for row in today_rows if time(9, 15) <= row[0].time() <= time(15, 30)]
    last = session_rows[-1] if session_rows else None
    market_open = (now.weekday() < 5 and time(9, 15) <= now.time() < time(15, 30))
    if last is None:
        return {"data_status": "AWAITING_DATA", "event": "MIXED", "direction": None,
                "last_candle_ist": None, "reason": "No completed index candles stored for this session."}
    age = now - last[0]
    fresh = market_open and timedelta(0) <= age <= timedelta(minutes=3)
    data_status = "LIVE_FRESH" if fresh else ("HISTORICAL" if not market_open else "STALE")
    rows = session_rows[-MAX_CANDLES:]
    last = rows[-1]
    stable = [_stable_direction(row) for row in rows]
    pressure = [_pressure_direction(row) for row in rows]
    recent = stable[:-2] if len(stable) > 2 else []
    prior_direction = next((direction for direction in reversed(recent) if direction), None)
    pressure_run = pressure[-2:] if len(pressure) >= 2 else []
    direction = (pressure_run[-1] if len(pressure_run) == 2 and pressure_run[0] == pressure_run[1]
                 else (stable[-1] if stable else None))
    confirmed = False
    if direction and len(rows) >= 3 and stable[-3:] == [direction, direction, direction]:
        closes = [row[1] for row in rows[-3:]]
        confirmed = (closes[0] < closes[1] < closes[2] if direction == "BULLISH"
                     else closes[0] > closes[1] > closes[2])
    if confirmed and prior_direction and prior_direction != direction:
        event = "CONFIRMED_SHIFT"
        reason = "Three completed candles align with EMA9/EMA20, momentum and closes after the prior opposite trend."
    elif (direction and prior_direction and prior_direction != direction
          and len(pressure_run) == 2 and pressure_run == [direction, direction]):
        event = "SHIFT_WATCH"
        reason = "Two completed closes and momentum have moved across EMA9 against the recent trend; EMA confirmation may still lag."
    elif stable[-1]:
        event = "TREND_" + stable[-1]
        direction = stable[-1]
        reason = "Current completed-candle EMA9/EMA20 and momentum agree; no new opposite shift is established."
    else:
        event = "MIXED"
        direction = None
        reason = "Completed-candle price, EMA and momentum do not yet align for a shift."
    if len(rows) < 3:
        event = "MIXED"
        direction = None
        reason = "Need at least three same-session completed candles before assessing a shift."
    if not fresh:
        reason = "Historical/stale data only. " + reason
    return {"data_status": data_status, "event": event, "direction": direction,
            "last_candle_ist": last[0].strftime("%Y-%m-%d %H:%M:%S"),
            "candles_used": len(rows), "prior_direction": prior_direction,
            "reason": reason}


def read_index_trend_changes(*, now=None, db_path=None):
    """Read today's completed index rows and return a freshness-labeled assessment."""
    now = now or datetime.now(IST)
    if now.tzinfo is None:
        raise ValueError("now must be timezone-aware")
    now = now.astimezone(IST)
    path = db_path or DB_PATH
    results = []
    try:
        with sqlite3.connect(path, timeout=5) as db:
            for symbol in INDEX_NAMES:
                rows = db.execute(
                    """SELECT candle_time, price, ema9, ema20, momentum
                       FROM (SELECT candle_time, price, ema9, ema20, momentum
                             FROM scanner_signal_history
                             WHERE symbol=? AND candle_time>=? AND candle_time<=?
                             ORDER BY candle_time DESC LIMIT ?) recent
                       ORDER BY candle_time ASC""",
                    (symbol, now.strftime("%Y-%m-%d 09:15:00"),
                     now.strftime("%Y-%m-%d 15:30:59"), MAX_CANDLES),
                ).fetchall()
                results.append({"symbol": symbol, **assess_index_shift(rows, now=now)})
    except sqlite3.Error as exc:
        return {"status": "UNAVAILABLE", "as_of_ist": now.isoformat(),
                "reason": type(exc).__name__, "indices": [
                    {"symbol": symbol, "data_status": "UNAVAILABLE", "event": "MIXED",
                     "direction": None, "last_candle_ist": None,
                     "reason": "Index trend history is unavailable."}
                    for symbol in INDEX_NAMES]}
    return {"status": "READY", "as_of_ist": now.isoformat(), "indices": results}
