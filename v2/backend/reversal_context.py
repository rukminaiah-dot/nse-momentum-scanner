"""Read-only current-session inputs for the pre-market reversal rule check.

This module deliberately reports inputs and rule readiness, not a probability.
P/E is descriptive context without a configured valuation baseline. FII/DII
cash-flow data is end-of-day and must never be shown as an intraday feed.
"""

from __future__ import annotations

import json
import math
import os
import sqlite3
import time
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from http.cookiejar import CookieJar
from typing import Any
from zoneinfo import ZoneInfo

from fastapi import APIRouter

from .database import DB_PATH
from .stock_universe import NIFTY_200

router = APIRouter()
IST = ZoneInfo("Asia/Kolkata")
RVOL_THRESHOLD = 1.5
_cache: dict[str, Any] | None = None
_cache_at = 0.0


def _number(value: Any) -> float | None:
    try:
        result = float(value)
        return result if math.isfinite(result) else None
    except (TypeError, ValueError, OverflowError):
        return None


def _get_json(url: str, headers: dict[str, str] | None = None) -> Any:
    request_headers = {"User-Agent": "Mozilla/5.0 NSE-Momentum-Scanner/1.0",
                       "Accept": "application/json"}
    request_headers.update(headers or {})
    request = urllib.request.Request(url, headers=request_headers)
    with urllib.request.urlopen(request, timeout=6) as response:
        return json.loads(response.read(2_000_000).decode("utf-8"))


def _nse_index_pe() -> dict[str, Any]:
    """Read the public NSE index snapshot; return unavailable on any schema drift."""
    now = datetime.now(timezone.utc).isoformat()
    try:
        jar = CookieJar()
        opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
        base_headers = {"User-Agent": "Mozilla/5.0 NSE-Momentum-Scanner/1.0",
                        "Accept": "text/html,application/xhtml+xml,application/json",
                        "Accept-Language": "en-US,en;q=0.9"}
        with opener.open(urllib.request.Request("https://www.nseindia.com/", headers=base_headers), timeout=6):
            pass
        req = urllib.request.Request("https://www.nseindia.com/api/allIndices",
                                     headers={**base_headers, "Referer": "https://www.nseindia.com/market-data/live-market-indices",
                                              "Accept": "application/json, text/plain, */*"})
        with opener.open(req, timeout=6) as response:
            payload = json.loads(response.read(2_000_000).decode("utf-8"))
        rows = payload.get("data") if isinstance(payload, dict) else None
        if not isinstance(rows, list):
            raise ValueError("NSE index response schema unavailable")
        row = next((item for item in rows if isinstance(item, dict)
                    and str(item.get("indexSymbol", "")).strip().upper() in {"NIFTY 50", "NIFTY50"}), None)
        pe = _number(row.get("pe")) if row else None
        if pe is None or pe <= 0:
            raise ValueError("NIFTY 50 P/E unavailable")
        source_time = row.get("timestamp") or payload.get("timestamp")
        return {"status": "AVAILABLE", "value": pe, "source": "NSE India index snapshot",
                "as_of": source_time or now, "fetched_at": now,
                "interpretation": "Context only; no cheap/expensive label without a chosen comparison baseline."}
    except Exception as exc:
        return {"status": "UNAVAILABLE", "value": None, "source": "NSE India index snapshot",
                "as_of": None, "fetched_at": now, "reason": type(exc).__name__}


def _upstox_get(path: str, params: list[tuple[str, str]], token: str) -> Any:
    query = urllib.parse.urlencode(params)
    return _get_json("https://api.upstox.com" + path + "?" + query,
                     {"Authorization": "Bearer " + token, "Accept": "application/json"})


def _upstox_quote(token: str) -> dict[str, Any]:
    now = datetime.now(timezone.utc).isoformat()
    try:
        payload = _upstox_get("/v3/market-quote/quotes",
                              [("instrument_key", "NSE_INDEX|India VIX")], token)
        data = payload.get("data") if isinstance(payload, dict) else None
        quote = data.get("NSE_INDEX:India VIX") if isinstance(data, dict) else None
        if not isinstance(quote, dict) and isinstance(data, dict):
            quote = next((item for key, item in data.items()
                          if isinstance(item, dict)
                          and str(key).split(":", 1)[-1].casefold() == "india vix"), None)
        if not isinstance(quote, dict):
            raise ValueError("India VIX quote missing")
        price = _number(quote.get("last_price"))
        prev = _number(quote.get("prev_close_price"))
        raw_stamp = quote.get("last_trade_time") or quote.get("timestamp")
        if not price or not prev or not raw_stamp:
            raise ValueError("India VIX quote incomplete")
        try:
            numeric_stamp = float(raw_stamp)
            stamp = datetime.fromtimestamp(numeric_stamp / 1000, timezone.utc).isoformat() if numeric_stamp > 10_000_000_000 else datetime.fromtimestamp(numeric_stamp, timezone.utc).isoformat()
        except (TypeError, ValueError, OverflowError, OSError):
            stamp = str(raw_stamp)
        change_pct = (price / prev - 1) * 100
        return {"status": "AVAILABLE", "value": price, "previous_close": prev,
                "change_pct": round(change_pct, 3), "as_of": stamp, "fetched_at": now,
                "source": "Upstox Full Market Quotes V3"}
    except Exception as exc:
        return {"status": "UNAVAILABLE", "value": None, "as_of": None, "fetched_at": now,
                "source": "Upstox Full Market Quotes V3", "reason": type(exc).__name__}


def _flow_record(token: str, path: str, flow_type: str, from_date: str) -> dict[str, Any]:
    now = datetime.now(timezone.utc).isoformat()
    try:
        payload = _upstox_get(path, [("data_type", "NSE_EQ|CASH"), ("interval", "1D"), ("from", from_date)], token)
        data = payload.get("data") if isinstance(payload, dict) else None
        rows = data.get("NSE_EQ|CASH") if isinstance(data, dict) else None
        if not isinstance(rows, list) or not rows:
            raise ValueError("cash flow rows missing")
        parsed = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            try:
                stamp = datetime.fromtimestamp(float(row["time_stamp"]) / 1000, timezone.utc)
            except (KeyError, TypeError, ValueError, OverflowError, OSError):
                continue
            buy, sell = _number(row.get("buy_amount")), _number(row.get("sell_amount"))
            if buy is None or sell is None or buy < 0 or sell < 0:
                continue
            parsed.append({"date": stamp.astimezone(IST).date().isoformat(),
                           "buy_cr": buy / 10_000_000, "sell_cr": sell / 10_000_000,
                           "net_cr": (buy - sell) / 10_000_000})
        parsed.sort(key=lambda item: item["date"], reverse=True)
        if not parsed:
            raise ValueError("no valid flow rows")
        return {"status": "AVAILABLE", "source": "Upstox Market Information API",
                "as_of_date": parsed[0]["date"], "latest": parsed[0], "recent": parsed[:5],
                "fetched_at": now, "type": flow_type}
    except Exception as exc:
        return {"status": "UNAVAILABLE", "source": "Upstox Market Information API",
                "as_of_date": None, "latest": None, "recent": [], "fetched_at": now,
                "type": flow_type, "reason": type(exc).__name__}


def _institutional_flows(token: str) -> dict[str, Any]:
    from_date = (datetime.now(IST).date() - timedelta(days=12)).isoformat()
    fii = _flow_record(token, "/v2/market/fii", "FII/FPI NSE cash", from_date)
    dii = _flow_record(token, "/v2/market/dii", "DII NSE cash", from_date)
    same_date = bool(fii["latest"] and dii["latest"] and fii["as_of_date"] == dii["as_of_date"])
    ratio = None
    if same_date:
        f_net = fii["latest"]["net_cr"]
        d_net = dii["latest"]["net_cr"]
        if f_net < 0 and d_net > 0:
            ratio = d_net / abs(f_net)
    return {"status": "AVAILABLE" if same_date else "UNAVAILABLE_OR_DATE_MISMATCH",
            "as_of_date": fii["as_of_date"] if same_date else None,
            "fii": fii, "dii": dii,
            "latest_absorption_ratio": round(ratio, 3) if ratio is not None else None,
            "latest_absorption_ratio_basis": "DII positive net cash flow / absolute FII negative net cash flow; same NSE cash date",
            "recent_5d": {"fii_net_cr": round(sum(x["net_cr"] for x in fii["recent"]), 2) if fii["recent"] else None,
                          "dii_net_cr": round(sum(x["net_cr"] for x in dii["recent"]), 2) if dii["recent"] else None},
            "publication_note": "Cash-market institutional activity is end-of-day data, not an intraday feed."}


def _observed_volume(now: datetime, session_open: bool) -> dict[str, Any]:
    result = {"status": "MARKET_CLOSED_HISTORICAL" if not session_open else "NO_FRESH_VOLUME_ROWS",
              "threshold_rvol": RVOL_THRESHOLD, "fresh_rows": 0, "verified_volume_rows": 0,
              "bullish_surge_rows": 0, "bearish_surge_rows": 0, "last_candle_ist": None,
              "source": "scanner_results; completed 1-minute candle volume / prior 19-candle mean"}
    if not session_open:
        return result
    try:
        with sqlite3.connect(DB_PATH, timeout=5) as db:
            db.row_factory = sqlite3.Row
            rows = db.execute("SELECT symbol,updated_at,rvol,current_volume,baseline_volume,signal,trend_5m FROM scanner_results").fetchall()
        eligible = set(NIFTY_200)
        for row in rows:
            if row["symbol"] not in eligible:
                continue
            try:
                stamp = datetime.strptime(row["updated_at"], "%Y-%m-%d %H:%M:%S").replace(tzinfo=IST)
            except (TypeError, ValueError):
                continue
            age = now - stamp
            if stamp.date() != now.date() or age < timedelta(0) or age > timedelta(minutes=3):
                continue
            result["fresh_rows"] += 1
            rvol = _number(row["rvol"])
            current, baseline = _number(row["current_volume"]), _number(row["baseline_volume"])
            if rvol is None or current is None or baseline is None or current < 0 or baseline <= 0:
                continue
            result["verified_volume_rows"] += 1
            if rvol >= RVOL_THRESHOLD and row["signal"] == "BUY" and row["trend_5m"] == "BULLISH":
                result["bullish_surge_rows"] += 1
            elif rvol >= RVOL_THRESHOLD and row["signal"] == "SELL" and row["trend_5m"] == "BEARISH":
                result["bearish_surge_rows"] += 1
            if result["last_candle_ist"] is None or stamp.isoformat() > result["last_candle_ist"]:
                result["last_candle_ist"] = stamp.isoformat()
        result["status"] = "AVAILABLE" if result["verified_volume_rows"] else "NO_VERIFIED_VOLUME_ROWS"
    except sqlite3.Error:
        result["status"] = "SCANNER_DATABASE_UNAVAILABLE"
    return result


def _rule_state(context: dict[str, Any]) -> dict[str, Any]:
    vix = context["india_vix"]
    flow = context["institutional_flows"]
    volume = context["volume"]
    live_price = context["price_structure"]["status"] == "LIVE_FRESH"
    if not live_price:
        return {"status": "LIVE_RULE_CHECK_PENDING", "summary": "Waiting for fresh Nifty candles during market hours.",
                "bottom_watch": False, "top_watch": False}
    missing = [name for name, available in (("India VIX", vix["status"] == "AVAILABLE"),
                                                ("same-date FII/DII cash", flow["status"] == "AVAILABLE"),
                                                ("verified completed-candle volume", volume["status"] == "AVAILABLE"))
               if not available]
    if missing:
        return {"status": "PARTIAL_INPUTS",
                "summary": "Rule check pending: unavailable inputs are " + ", ".join(missing) + ". No reversal state is assigned.",
                "bottom_watch": False, "top_watch": False,
                "valuation_note": "Nifty P/E is context only and does not gate the rule check."}
    direction = context["price_structure"].get("direction")
    vix_stress_falling = vix["value"] >= 25 and vix.get("change_pct", 0) < 0
    vix_rising = vix.get("change_pct", 0) >= 5
    absorption = flow.get("latest_absorption_ratio")
    bottom_support_count = sum((vix_stress_falling,
                                absorption is not None and absorption >= 1,
                                volume.get("bullish_surge_rows", 0) > 0))
    top_support_count = sum((vix_rising,
                             (flow["fii"].get("latest") or {}).get("net_cr", 0) < 0,
                             volume.get("bearish_surge_rows", 0) > 0))
    bottom = direction == "BULLISH" and bottom_support_count >= 2
    top = direction == "BEARISH" and top_support_count >= 2
    if bottom:
        summary = "Potential bottom reversal watch: fresh bullish structure plus at least two of three confirmations. Confirmation remains incomplete."
    elif top:
        summary = "Potential top reversal watch: fresh bearish structure plus at least two of three confirmations. Confirmation remains incomplete."
    else:
        summary = "No current reversal watch is triggered by the available rules."
    return {"status": "WATCH_ONLY" if bottom or top else "NO_REVERSAL_WATCH",
            "summary": summary, "bottom_watch": bottom, "top_watch": top,
            "valuation_note": "Nifty P/E is displayed as context only; no valuation threshold is inferred from one reading."}


@router.get("/api/v2/reversal-context")
def reversal_context() -> dict[str, Any]:
    """Current Nifty reversal rule inputs; cash flows and prices retain source times."""
    global _cache, _cache_at
    now_epoch = time.monotonic()
    if _cache is not None and now_epoch - _cache_at < 30:
        return _cache
    now = datetime.now(IST)
    session_open = now.weekday() < 5 and datetime.strptime("09:15", "%H:%M").time() <= now.time() < datetime.strptime("15:30", "%H:%M").time()
    token = (os.environ.get("UPSTOX_ANALYTICS_TOKEN")
             or os.environ.get("UPSTOX_ACCESS_TOKEN", "")).strip()
    pe = _nse_index_pe()
    vix = _upstox_quote(token) if token else {"status": "TOKEN_NOT_CONFIGURED", "value": None, "as_of": None, "source": "Upstox"}
    flows = _institutional_flows(token) if token else {"status": "TOKEN_NOT_CONFIGURED", "fii": {"status": "TOKEN_NOT_CONFIGURED"}, "dii": {"status": "TOKEN_NOT_CONFIGURED"}, "latest_absorption_ratio": None, "as_of_date": None}
    volume = _observed_volume(now, session_open)
    index_row = None
    try:
        with sqlite3.connect(DB_PATH, timeout=5) as db:
            db.row_factory = sqlite3.Row
            found = db.execute("SELECT symbol,updated_at,price,ema9,ema20,momentum,trend_5m,signal FROM scanner_results WHERE upper(symbol)='NIFTY 50' LIMIT 1").fetchone()
            index_row = dict(found) if found else None
    except sqlite3.Error:
        pass
    direction = None
    candle_time = None
    price = None
    status = "UNAVAILABLE"
    if index_row:
        candle_time = index_row.get("updated_at")
        price = _number(index_row.get("price"))
        e9, e20, momentum = (_number(index_row.get(k)) for k in ("ema9", "ema20", "momentum"))
        try:
            stamp = datetime.strptime(candle_time, "%Y-%m-%d %H:%M:%S").replace(tzinfo=IST)
            age = now - stamp
            if session_open and stamp.date() == now.date() and timedelta(0) <= age <= timedelta(minutes=3):
                status = "LIVE_FRESH"
                if e9 is not None and e20 is not None and momentum is not None:
                    direction = "BULLISH" if e9 > e20 and momentum > 0 else "BEARISH" if e9 < e20 and momentum < 0 else "MIXED"
            else:
                status = "HISTORICAL"
        except (TypeError, ValueError):
            status = "STALE"
    context = {"status": "READY" if pe["status"] == "AVAILABLE" else "PARTIAL",
               "as_of_ist": now.isoformat(), "market_session": "OPEN" if session_open else "CLOSED",
               "price_structure": {"status": status, "direction": direction, "price": price, "candle_ist": candle_time,
                                   "basis": "latest Nifty scanner row; 5-minute EMA9/EMA20 and momentum"},
               "nifty_pe": pe, "india_vix": vix, "institutional_flows": flows, "volume": volume,
               "rules": None, "order_execution_enabled": False}
    context["rules"] = _rule_state(context)
    _cache, _cache_at = context, now_epoch
    return context
