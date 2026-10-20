"""Read-only current-session inputs for the pre-market reversal rule check.

This module deliberately reports inputs and rule readiness, not a probability.
P/E is descriptive context without a configured valuation baseline. FII/DII
cash-flow data is end-of-day and must never be shown as an intraday feed.
"""

from __future__ import annotations

import json
import math
import os
import re
import sqlite3
import threading
import time
import urllib.parse
import urllib.request
from datetime import date, datetime, time as clock_time, timedelta, timezone
from http.cookiejar import CookieJar
from html.parser import HTMLParser
from typing import Any
from zoneinfo import ZoneInfo

from fastapi import APIRouter

from .database import DB_PATH
from .five_session_rules import event_spec, rule_definition
from .long_horizon_reversal import rule_definition as long_horizon_rule_definition
from .nifty_pe_archive import read_latest_nifty_pe, save_daily_nifty_pe
from .stock_universe import NIFTY_200

router = APIRouter()
IST = ZoneInfo("Asia/Kolkata")
RVOL_THRESHOLD = 1.5
FLOW_FRESHNESS_DAYS = 4
_cache: dict[str, Any] | None = None
_cache_at = 0.0
_flow_cache: dict[str, Any] | None = None
_flow_cache_date = None
_flow_cache_lock = threading.Lock()
_pe_cache: dict[str, Any] | None = None
_pe_cache_date: date | None = None
_pe_last_attempt: datetime | None = None
_pe_cache_lock = threading.Lock()
PE_DAILY_REFRESH_AFTER = clock_time(16, 0)
PE_REFRESH_RETRY_MINUTES = 30


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


def _nse_pe_session_date(raw_timestamp: Any) -> tuple[str, str] | None:
    """Return a source-reported session date and display timestamp, without inventing one."""
    if not isinstance(raw_timestamp, str) or not raw_timestamp.strip():
        return None
    raw = raw_timestamp.strip()
    for fmt in ("%d-%b-%Y %H:%M:%S", "%d-%b-%Y %H:%M", "%d-%b-%Y",
                "%d-%m-%Y %H:%M:%S", "%d-%m-%Y %H:%M", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            parsed = datetime.strptime(raw, fmt)
            return parsed.date().isoformat(), raw
        except ValueError:
            continue
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=IST)
        return parsed.astimezone(IST).date().isoformat(), parsed.isoformat()
    except ValueError:
        return None


def _daily_pe_result(record: dict[str, Any] | None, now: datetime, storage: str,
                     fetch_error: str | None = None) -> dict[str, Any]:
    if not record:
        return {"status": "UNAVAILABLE", "value": None,
                "source": "NSE Indices daily valuation snapshot", "as_of": None,
                "session_date": None, "fetched_at": None, "storage": storage,
                "refresh_status": "FAILED" if fetch_error else "AWAITING_DAILY_SNAPSHOT",
                "reason": fetch_error}
    today = now.astimezone(IST).date().isoformat()
    same_day = record.get("session_date") == today
    return {"status": "AVAILABLE" if same_day else "HISTORICAL",
            "freshness": "DAILY_EOD" if same_day else "LAST_STORED_DAILY_READING",
            "value": record.get("value"), "source": record.get("source") or "NSE Indices",
            "as_of": record.get("as_of"), "session_date": record.get("session_date"),
            "fetched_at": record.get("fetched_at"), "basis": record.get("basis") or "",
            "storage": storage,
            "refresh_status": "FAILED_USING_LAST_STORED" if fetch_error else ("UPDATED_TODAY" if same_day else "NO_TODAY_SNAPSHOT"),
            "reason": fetch_error,
            "interpretation": "Daily end-of-day context only; not a live valuation signal."}


def _fetch_daily_nifty_pe(now: datetime) -> dict[str, Any]:
    """Fetch the official NSE index snapshot once the daily close is published."""
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
    source_timestamp = (row.get("timestamp") or row.get("date")
                        or payload.get("timestamp") or payload.get("date"))
    parsed = _nse_pe_session_date(source_timestamp)
    if not parsed:
        raise ValueError("NSE P/E source date unavailable")
    session_date, as_of = parsed
    record = {"session_date": session_date, "value": pe, "as_of": as_of,
              "fetched_at": now.astimezone(timezone.utc).isoformat(),
              "source": "NSE India index snapshot (daily close)",
              "basis": "NSE index P/E; trailing constituent earnings as published by NSE Indices"}
    return record


def _nse_index_pe(now: datetime | None = None) -> dict[str, Any]:
    """Return today's end-of-day NIFTY P/E, or the last stored dated reading."""
    global _pe_cache, _pe_cache_date, _pe_last_attempt
    now = (now or datetime.now(IST)).astimezone(IST)
    today = now.date()
    now_utc = now.astimezone(timezone.utc)
    with _pe_cache_lock:
        if _pe_cache is not None and _pe_cache_date == today:
            if _pe_cache.get("status") == "AVAILABLE":
                return _pe_cache
            if _pe_last_attempt and now_utc - _pe_last_attempt < timedelta(minutes=PE_REFRESH_RETRY_MINUTES):
                return _pe_cache

        record, storage = read_latest_nifty_pe()
        can_refresh = (now.weekday() < 5 and now.time() >= PE_DAILY_REFRESH_AFTER)
        if not can_refresh:
            result = _daily_pe_result(record, now, storage)
            _pe_cache, _pe_cache_date = result, today
            return result
        if record and record.get("session_date") == today.isoformat():
            result = _daily_pe_result(record, now, storage)
            _pe_cache, _pe_cache_date = result, today
            return result

        _pe_last_attempt = now_utc
        try:
            new_record = _fetch_daily_nifty_pe(now)
            if new_record["session_date"] > today.isoformat():
                raise ValueError("NSE P/E source date is after the current date")
            storage = save_daily_nifty_pe(new_record)
            result = _daily_pe_result(new_record, now, storage)
            if new_record["session_date"] == today.isoformat():
                _pe_cache, _pe_cache_date = result, today
                return result
            # Holiday/late-published snapshot: preserve its actual source date.
            record, storage = new_record, storage
        except Exception as exc:
            fetch_error = type(exc).__name__
            result = _daily_pe_result(record, now, storage, fetch_error)
            _pe_cache, _pe_cache_date = result, today
            return result
        result = _daily_pe_result(record, now, storage)
        _pe_cache, _pe_cache_date = result, today
        return result


def _upstox_get(path: str, params: list[tuple[str, str]], token: str) -> Any:
    query = urllib.parse.urlencode(params)
    return _get_json("https://api.upstox.com" + path + "?" + query,
                     {"Authorization": "Bearer " + token, "Accept": "application/json"})


def _quote_timestamp(raw_stamp: Any) -> datetime:
    """Parse Upstox quote timestamps in epoch seconds/ms or ISO-8601 form."""
    if raw_stamp is None or isinstance(raw_stamp, bool):
        raise ValueError("quote timestamp unavailable")
    try:
        numeric_stamp = float(raw_stamp)
    except (TypeError, ValueError, OverflowError):
        numeric_stamp = None
    if numeric_stamp is not None and math.isfinite(numeric_stamp) and numeric_stamp > 0:
        seconds = numeric_stamp / 1000 if numeric_stamp >= 10_000_000_000 else numeric_stamp
        return datetime.fromtimestamp(seconds, timezone.utc)
    stamp_text = str(raw_stamp).strip()
    if not stamp_text:
        raise ValueError("quote timestamp unavailable")
    stamp = datetime.fromisoformat(stamp_text.replace("Z", "+00:00"))
    if stamp.tzinfo is None:
        stamp = stamp.replace(tzinfo=timezone.utc)
    return stamp.astimezone(timezone.utc)


def _quote_freshness(stamp: datetime, now: datetime | None = None) -> tuple[str, float]:
    """Only treat an India VIX quote as live during the NSE session when recent."""
    now = now or datetime.now(timezone.utc)
    local_now = now.astimezone(IST)
    session_open = (local_now.weekday() < 5
                    and datetime.strptime("09:15", "%H:%M").time() <= local_now.time()
                    < datetime.strptime("15:30", "%H:%M").time())
    age_seconds = (now.astimezone(timezone.utc) - stamp.astimezone(timezone.utc)).total_seconds()
    if not session_open:
        return "HISTORICAL", round(age_seconds, 1)
    if -120 <= age_seconds <= 15 * 60:
        return "AVAILABLE", round(max(0, age_seconds), 1)
    return "STALE", round(age_seconds, 1)


def _upstox_quote(tokens: str | list[str]) -> dict[str, Any]:
    now = datetime.now(timezone.utc).isoformat()
    response_keys = []
    quote_fields = []
    field_presence: dict[str, bool] = {}
    try:
        candidates = list(dict.fromkeys(
            item.strip() for item in (tokens if isinstance(tokens, list) else [tokens])
            if item and item.strip()
        ))
        quote = None
        quote_source = "Upstox Full Market Quotes"
        last_error = None
        # Try each configured quote token, V3 first and V2 for compatibility.
        for candidate in candidates:
            for quote_path in ("/v3/market-quote/quotes", "/v2/market-quote/quotes"):
                try:
                    payload = _upstox_get(quote_path,
                                          [("instrument_key", "NSE_INDEX|India VIX")], candidate)
                    data = payload.get("data") if isinstance(payload, dict) else None
                    response_keys = list(data.keys())[:12] if isinstance(data, dict) else []
                    quote = data.get("NSE_INDEX:India VIX") if isinstance(data, dict) else None
                    if not isinstance(quote, dict) and isinstance(data, dict):
                        quote = next((item for key, item in data.items()
                                      if isinstance(item, dict)
                                      and str(key).split(":", 1)[-1].casefold() == "india vix"), None)
                    if isinstance(quote, dict):
                        quote_source = ("Upstox Full Market Quotes V3" if quote_path.startswith("/v3/")
                                        else "Upstox Full Market Quotes V2")
                        break
                    last_error = ValueError("India VIX quote missing")
                except Exception as exc:
                    last_error = exc
            if isinstance(quote, dict):
                break
        if not isinstance(quote, dict):
            raise last_error or ValueError("India VIX quote missing")
        quote_fields = sorted(str(key) for key in quote.keys())
        field_presence = {key: key in quote and quote.get(key) is not None
                          for key in ("last_price", "prev_close_price", "net_change",
                                      "last_trade_time", "timestamp")}
        price = _number(quote.get("last_price"))
        prev = _number(quote.get("prev_close_price"))
        # Some quote payloads can omit prev_close_price while still supplying
        # Upstox's documented net_change. Reconstruct only from those source fields.
        net_change = _number(quote.get("net_change"))
        if prev is None and price is not None and net_change is not None:
            prev = price - net_change
        raw_stamp = quote.get("last_trade_time") or quote.get("timestamp")
        if price is None or price <= 0 or prev is None or prev <= 0 or raw_stamp is None:
            raise ValueError("India VIX quote incomplete")
        stamp = _quote_timestamp(raw_stamp)
        freshness, age_seconds = _quote_freshness(stamp)
        change_pct = (price / prev - 1) * 100
        return {"status": freshness, "value": price, "previous_close": prev,
                "change_pct": round(change_pct, 3), "as_of": stamp.isoformat(), "fetched_at": now,
                "source": quote_source, "response_keys": response_keys,
                "quote_fields": quote_fields, "field_presence": field_presence,
                "age_seconds": age_seconds, "freshness_threshold_seconds": 900}
    except Exception as exc:
        return {"status": "UNAVAILABLE", "value": None, "as_of": None, "fetched_at": now,
                "source": quote_source, "reason": type(exc).__name__,
                "response_keys": response_keys, "quote_fields": quote_fields,
                "field_presence": field_presence}


class _CashFlowTableParser(HTMLParser):
    """Extract the table rows rendered on Upstox's public FII/DII page."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.tables: list[list[list[str]]] = []
        self._table: list[list[str]] | None = None
        self._row: list[str] | None = None
        self._cell: list[str] | None = None

    def handle_starttag(self, tag, attrs):
        tag = tag.lower()
        if tag == "table":
            self._table = []
        elif tag == "tr" and self._table is not None:
            self._row = []
        elif tag in ("th", "td") and self._row is not None:
            self._cell = []

    def handle_data(self, data):
        if self._cell is not None:
            self._cell.append(data)

    def handle_endtag(self, tag):
        tag = tag.lower()
        if tag in ("th", "td") and self._cell is not None and self._row is not None:
            self._row.append(" ".join("".join(self._cell).split()))
            self._cell = None
        elif tag == "tr" and self._row is not None and self._table is not None:
            if self._row:
                self._table.append(self._row)
            self._row = None
        elif tag == "table" and self._table is not None:
            self.tables.append(self._table)
            self._table = None


def _parse_upstox_cash_table(html: str, fetched_at: str | None = None) -> dict[str, Any]:
    """Parse reported daily net cash flows; fail closed if Upstox changes schema."""
    if not isinstance(html, str) or not html:
        raise ValueError("Upstox FII/DII page was empty")
    parser = _CashFlowTableParser()
    parser.feed(html)
    expected = ("date", "fii net purchase/sales (cr.)", "dii net purchase/sales (cr.)")
    table = next((rows for rows in parser.tables if rows and
                  all(any(" ".join(cell.casefold().split()) == label for row in rows[:2] for cell in row)
                      for label in expected)), None)
    if table is None:
        raise ValueError("Upstox cash table columns unavailable")

    headers = [" ".join(cell.casefold().split()) for cell in table[0]]
    date_index = headers.index("date")
    fii_index = headers.index("fii net purchase/sales (cr.)")
    dii_index = headers.index("dii net purchase/sales (cr.)")
    parsed = []
    for row in table[1:]:
        if max(date_index, fii_index, dii_index) >= len(row):
            continue
        try:
            report_date = datetime.strptime(row[date_index].strip(), "%d-%m-%Y").date()
            values = []
            for index in (fii_index, dii_index):
                raw = re.sub(r"\s+", "", row[index].replace("₹", "").replace(",", "").strip())
                number = _number(raw)
                if number is None:
                    raise ValueError("Invalid cash flow value")
                values.append(number)
            parsed.append((report_date, values[0], values[1]))
        except (TypeError, ValueError, OverflowError):
            continue
    parsed.sort(key=lambda item: item[0], reverse=True)
    if not parsed:
        raise ValueError("Upstox cash table has no valid rows")

    latest_date = parsed[0][0].isoformat()
    fii_net, dii_net = parsed[0][1], parsed[0][2]
    fii_recent = [{"date": d.isoformat(), "net_cr": fii} for d, fii, _ in parsed[:5]]
    dii_recent = [{"date": d.isoformat(), "net_cr": dii} for d, _, dii in parsed[:5]]
    return {
        "status": "AVAILABLE", "source": "Upstox FII/DII data page · NSE cash · daily",
        "as_of_date": latest_date,
        "fii": {"status": "AVAILABLE", "source": "Upstox FII/DII data page · NSE cash",
                "as_of_date": latest_date, "latest": {"date": latest_date, "net_cr": fii_net},
                "recent": fii_recent, "type": "FII/FPI NSE cash"},
        "dii": {"status": "AVAILABLE", "source": "Upstox FII/DII data page · NSE cash",
                "as_of_date": latest_date, "latest": {"date": latest_date, "net_cr": dii_net},
                "recent": dii_recent, "type": "DII NSE cash"},
        "latest_absorption_ratio": round(dii_net / abs(fii_net), 3) if fii_net < 0 < dii_net else None,
        "latest_absorption_ratio_basis": "DII positive net cash flow / absolute FII negative net cash flow; same NSE cash date",
        "recent_5d": {"fii_net_cr": round(sum(item[1] for item in parsed[:5]), 2),
                      "dii_net_cr": round(sum(item[2] for item in parsed[:5]), 2)},
        "fetched_at": fetched_at or datetime.now(timezone.utc).isoformat(),
        "publication_note": "Cash-market institutional activity is end-of-day data, not an intraday feed.",
    }


def _fetch_upstox_cash_flows() -> dict[str, Any]:
    request = urllib.request.Request(
        "https://upstox.com/fii-dii-data/",
        headers={"User-Agent": "Mozilla/5.0 NSE-Momentum-Scanner/1.0",
                 "Accept": "text/html,application/xhtml+xml"},
    )
    with urllib.request.urlopen(request, timeout=10) as response:
        html = response.read(2_000_000).decode("utf-8", "replace")
    return _parse_upstox_cash_table(html)


def _institutional_flows(now: datetime | None = None) -> dict[str, Any]:
    """Fetch the public Upstox cash report once per IST day after its publication window."""
    global _flow_cache, _flow_cache_date
    now = (now or datetime.now(IST)).astimezone(IST)
    today = now.date()
    if _flow_cache is not None and _flow_cache_date == today:
        return _flow_cache
    if now.time() < clock_time(8, 45):
        return {"status": "AWAITING_DAILY_PUBLICATION", "source": "Upstox FII/DII data page · NSE cash · daily",
                "as_of_date": None, "freshness": "UNKNOWN", "fii": {"status": "UNAVAILABLE"},
                "dii": {"status": "UNAVAILABLE"}, "latest_absorption_ratio": None,
                "publication_note": "Daily cash report is fetched once after the expected Upstox publication window."}
    with _flow_cache_lock:
        if _flow_cache is not None and _flow_cache_date == today:
            return _flow_cache
        try:
            result = _fetch_upstox_cash_flows()
            result["freshness"] = _flow_freshness(result.get("as_of_date"), today=today)
            result["status"] = ("AVAILABLE" if result["fii"]["latest"]["date"] == result["dii"]["latest"]["date"]
                                else "UNAVAILABLE_OR_DATE_MISMATCH")
        except Exception as exc:
            result = {"status": "UNAVAILABLE", "source": "Upstox FII/DII data page · NSE cash · daily",
                      "as_of_date": None, "freshness": "UNKNOWN", "fii": {"status": "UNAVAILABLE"},
                      "dii": {"status": "UNAVAILABLE"}, "latest_absorption_ratio": None,
                      "fetched_at": datetime.now(timezone.utc).isoformat(), "reason": type(exc).__name__,
                      "publication_note": "Cash-market institutional activity is end-of-day data, not an intraday feed."}
        _flow_cache, _flow_cache_date = result, today
        return result


def _flow_freshness(as_of_date: str | None, today=None) -> str:
    """Only use recent end-of-day cash flows as a current-session confirmation."""
    if not as_of_date:
        return "UNKNOWN"
    try:
        report_date = datetime.strptime(as_of_date, "%Y-%m-%d").date()
        age_days = ((today or datetime.now(IST).date()) - report_date).days
    except (TypeError, ValueError):
        return "UNKNOWN"
    return "CURRENT" if 0 <= age_days <= FLOW_FRESHNESS_DAYS else "STALE"


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
                                                ("recent same-date FII/DII cash", flow["status"] == "AVAILABLE" and flow.get("freshness") == "CURRENT"),
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
    quote_tokens = list(dict.fromkeys(
        value.strip() for value in (
            os.environ.get("UPSTOX_ACCESS_TOKEN", ""),
            os.environ.get("UPSTOX_ANALYTICS_TOKEN", ""),
        ) if value and value.strip()
    ))
    pe = _nse_index_pe()
    vix = _upstox_quote(quote_tokens) if quote_tokens else {"status": "TOKEN_NOT_CONFIGURED", "value": None, "as_of": None, "source": "Upstox"}
    flows = _institutional_flows()
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
               "five_session": {"event": event_spec(), **rule_definition()},
               "long_horizon_reversal": long_horizon_rule_definition(),
               "rules": None, "order_execution_enabled": False}
    context["rules"] = _rule_state(context)
    _cache, _cache_at = context, now_epoch
    return context
