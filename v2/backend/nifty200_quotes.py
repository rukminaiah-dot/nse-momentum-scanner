"""Validation helpers for Upstox NIFTY 200 session-change quotes."""

from datetime import datetime, timezone
from zoneinfo import ZoneInfo


def quote_change_fields(
    symbol,
    instrument_key,
    quotes,
    quote_error=None,
    market_open=False,
    *,
    now_utc=None,
):
    """Return a verified previous-close change record or an explicit unavailable state."""
    if not isinstance(quotes, dict):
        quotes = {}
    expected = str(instrument_key).replace("|", ":").casefold()
    quote = quotes.get(expected)
    if not isinstance(quote, dict):
        quote = next((
            value for response_key, value in quotes.items()
            if isinstance(response_key, str) and isinstance(value, dict)
            and response_key.split(":", 1)[-1].casefold() == str(symbol).casefold()
        ), None)
    if not quote:
        return {
            "daily_change_pct": None, "previous_close": None,
            "quote_price": None, "quote_time_ist": None,
            "change_status": "UNAVAILABLE" if quote_error else "NO_QUOTE",
        }
    try:
        price = float(quote["last_price"])
        previous_close = quote.get("prev_close_price")
        if previous_close is None and quote.get("net_change") is not None:
            previous_close = price - float(quote["net_change"])
        previous_close = float(previous_close)
        if not (price > 0 and previous_close > 0):
            raise ValueError("Invalid quote prices")
        raw_time = quote.get("last_trade_time") or quote.get("timestamp")
        if raw_time is None:
            raise ValueError("Missing quote timestamp")
        if isinstance(raw_time, (int, float)) or str(raw_time).isdigit():
            timestamp = float(raw_time)
            if timestamp > 100000000000:
                timestamp /= 1000.0
            traded_at = datetime.fromtimestamp(timestamp, timezone.utc)
        else:
            traded_at = datetime.fromisoformat(str(raw_time).replace("Z", "+00:00"))
            if traded_at.tzinfo is None:
                raise ValueError("Naive quote timestamp")
            traded_at = traded_at.astimezone(timezone.utc)
        now = now_utc or datetime.now(timezone.utc)
        if now.tzinfo is None:
            raise ValueError("Naive current timestamp")
        age_seconds = (now.astimezone(timezone.utc) - traded_at).total_seconds()
        quote_time_ist = traded_at.astimezone(ZoneInfo("Asia/Kolkata")).isoformat()
        freshness_limit = 900 if market_open else 36 * 60 * 60
        if age_seconds < -120 or age_seconds > freshness_limit:
            return {
                "daily_change_pct": None, "previous_close": previous_close,
                "quote_price": price, "quote_time_ist": quote_time_ist,
                "change_status": "STALE",
            }
        return {
            "daily_change_pct": (price - previous_close) / previous_close * 100,
            "previous_close": previous_close, "quote_price": price,
            "quote_time_ist": quote_time_ist,
            "change_status": "CURRENT" if market_open else "LAST_SESSION",
        }
    except (KeyError, TypeError, ValueError, OverflowError, OSError):
        return {
            "daily_change_pct": None, "previous_close": None,
            "quote_price": None, "quote_time_ist": None,
            "change_status": "INVALID_QUOTE",
        }
