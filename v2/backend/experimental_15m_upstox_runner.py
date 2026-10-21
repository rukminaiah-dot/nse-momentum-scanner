"""Opt-in, standalone Upstox 15m PAPER screening runner.

Usage (local or staging only):
    python -m v2.backend.experimental_15m_upstox_runner --limit 5

Uses the existing UPSTOX_ACCESS_TOKEN environment variable. Never sends orders,
never touches production scanner state, and is not invoked by start_v2.sh.
"""
import argparse
import json
import os
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from .experimental_15m_pipeline import screen_universe
from .stock_universe import NIFTY_200

IST = ZoneInfo("Asia/Kolkata")


def _parse_rows(rows):
    bars = []
    for row in rows or ():
        try:
            stamp = datetime.fromisoformat(row[0].replace("Z", "+00:00"))
            if stamp.tzinfo is None:
                raise ValueError("timestamp must be timezone-aware")
            stamp = stamp.astimezone(IST).replace(tzinfo=None)
            bar = {"timestamp": stamp, "open": float(row[1]),
                   "high": float(row[2]), "low": float(row[3]),
                   "close": float(row[4]), "volume": float(row[5])}
            bars.append(bar)
        except (IndexError, TypeError, ValueError, AttributeError):
            continue
    # Duplicated timestamps are unsafe; preserve duplicates for rejection
    # by the continuity / baseline checks rather than silently deduplicating.
    return sorted(bars, key=lambda bar: bar["timestamp"])


def fetch_symbol(api, key, *, now, lookback_days=90):
    """Fetch 15m historical + current intraday bars for one instrument."""
    today = now.date()
    yesterday = today - timedelta(days=1)
    since = yesterday - timedelta(days=lookback_days)
    historical = api.get_historical_candle_data1(
        key, "minutes", "15", str(yesterday), str(since))
    history = _parse_rows(historical.data.candles or [])
    del historical
    intraday = api.get_intra_day_candle_data(key, "minutes", "15")
    current = _parse_rows(intraday.data.candles or [])
    del intraday
    # Keep historical candles only for indicators, current-session candles
    # for signal freshness; never include today's incomplete 15m candle.
    complete = [bar for bar in current
                if bar["timestamp"].date() == today and
                bar["timestamp"] + timedelta(minutes=15) <= now]
    # Historical API data must never be used as same-day live evidence.\n    # Retain enough previous-session candles for EMA50 and Stoch RSI.\n    return (history[-100:] + complete), history


def run(*, limit=5, now=None, api=None):
    if not 1 <= limit <= len(NIFTY_200):
        raise ValueError("limit must be between 1 and the NSE universe size")
    now = now or datetime.now(IST).replace(tzinfo=None)
    if now.tzinfo is not None:
        now = now.astimezone(IST).replace(tzinfo=None)
    if api is None:
        import upstox_client
        token = os.environ["UPSTOX_ACCESS_TOKEN"]
        config = upstox_client.Configuration()
        config.access_token = token
        api = upstox_client.HistoryV3Api(upstox_client.ApiClient(config))
    stock_bars, historical_bars, errors = {}, {}, {}
    for symbol, key in list(NIFTY_200.items())[:limit]:
        try:
            stock_bars[symbol], historical_bars[symbol] = fetch_symbol(
                api, key, now=now)
        except Exception as exc:
            errors[symbol] = type(exc).__name__
    result = screen_universe(stock_bars, historical_bars, now=now)
    result["fetch_errors"] = errors
    result["requested_count"] = limit
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=5)\n    parser.add_argument("--offline", action="store_true", help="Do not contact Upstox; print an empty paper result")
    args = parser.parse_args()
    if args.offline:\n        result = {"mode": "PAPER", "selected_count": 0, "selected": [],\n                  "reason": "OFFLINE_NO_MARKET_DATA", "requested_count": args.limit}\n    else:\n        result = run(limit=args.limit)
    print(json.dumps(result, default=str, sort_keys=True))


if __name__ == "__main__":
    main()
