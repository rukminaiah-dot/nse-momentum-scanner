"""Read-only daily NSE historical collector with explicit progress and fail-closed signals.

The preview's in-memory cache resets on Render restarts. No trades are placed.
"""
import threading
import time
import json
import os
from pathlib import Path
from datetime import date, timedelta
from v2.backend.nse_daily_source import download_session
from v2.backend.investment_watchlist_57 import RESEARCH_UNIVERSE
from v2.backend.verified_positional_signals import evaluate

_lock = threading.Lock()
_CACHE_PATH = Path(os.environ.get("NSE_HISTORY_CACHE_PATH", "/tmp/nse_investment_history.json"))
_CACHE_IS_DURABLE = bool(os.environ.get("NSE_HISTORY_CACHE_PATH"))
_history = {s: [] for s in RESEARCH_UNIVERSE}
_market_discovery = {"session": None, "universe_count": 0, "candidates": [], "status": "AWAITING_NSE_SESSION"}
_state = {"status":"NOT_STARTED","sessions":0,"attempted":0,"errors":0,"latest_session":None,
          "source":"NSE official CM-UDiFF daily bhavcopy", "persistence":"configured disk path" if _CACHE_IS_DURABLE else "temporary disk cache (lost on restart)"}

def _save_cache():
    """Atomic cache write; durable only if configured on a persistent mounted disk."""
    try:
        _CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
        temp = _CACHE_PATH.with_suffix(".tmp")
        with _lock:
            payload = {"history": _history, "state": dict(_state)}
        temp.write_text(json.dumps(payload), encoding="utf-8")
        os.replace(temp, _CACHE_PATH)
    except Exception as exc:
        print("NSE_CACHE_WRITE_ERROR:", type(exc).__name__, flush=True)

def _restore_cache():
    try:
        payload = json.loads(_CACHE_PATH.read_text(encoding="utf-8"))
        stored = payload["history"]
        if not isinstance(stored, dict):
            return
        with _lock:
            if _market_discovery["session"] is None:
                # New symbols are discoverable without manually editing the 57-stock list.
                # A strong daily candle is only a lead; valuation and filings are still required.
                candidates = []
                for symbol, row in report.items():
                    op, close, volume = row.get("open"), row.get("close"), row.get("volume")
                    if not (isinstance(op, (int, float)) and isinstance(close, (int, float))
                            and isinstance(volume, (int, float)) and op > 0 and close > 0
                            and volume >= 100000 and close >= 20):
                        continue
                    daily_move = (close / op - 1) * 100
                    if 2 <= daily_move <= 12:
                        candidates.append({"symbol": symbol, "nse_close": close, "daily_open_to_close_pct": round(daily_move, 2),
                                           "volume": volume, "already_in_research": symbol in RESEARCH_UNIVERSE,
                                           "rating": "DISCOVERY_ONLY_NOT_SCORED"})
                candidates.sort(key=lambda item: (-item["daily_open_to_close_pct"], -item["volume"]))
                _market_discovery.update(session=day.isoformat(), universe_count=len(report),
                                         candidates=candidates[:50], status="DAILY_PRICE_DISCOVERY_ONLY")
            for symbol in RESEARCH_UNIVERSE:
                rows = stored.get(symbol, [])
                if isinstance(rows, list):
                    _history[symbol] = [row for row in rows if isinstance(row, dict)
                        and isinstance(row.get("date"), str)
                        and all(isinstance(row.get(k), (int, float)) for k in ("open","high","low","close","volume"))]
            _state["status"] = "CACHED_REFRESHING"
            _state["sessions"] = len(set(row["date"] for rows in _history.values() for row in rows))
            _state["latest_session"] = max((row["date"] for rows in _history.values() for row in rows), default=None)
        print("NSE_CACHE_RESTORED:", _state["sessions"], flush=True)
    except (OSError, ValueError, KeyError, TypeError):
        pass

def market_discovery():
    """Market-wide NSE EQ discovery, NOT a valuation or Buy screen."""
    with _lock:
        return dict(_market_discovery)

def snapshot():
    with _lock:
        return dict(_state, stocks_with_70_sessions=sum(len(v)>=70 for v in _history.values()),
                    watchlist_count=len(RESEARCH_UNIVERSE),
                    insufficient_symbols=[{"symbol":s,"sessions":len(v)} for s,v in _history.items() if len(v)<70])

def latest_closes():
    """Last verified completed NSE closing candle for each base watchlist stock."""
    with _lock:
        result = []
        for symbol, rows in _history.items():
            if rows:
                row = max(rows, key=lambda item: item["date"])
                result.append({"symbol": symbol, "price": row["close"],
                               "session": row["date"], "status": "NSE_DAILY_CLOSE_NOT_LIVE"})
            else:
                result.append({"symbol": symbol, "price": None, "session": None,
                               "status": "NO_VERIFIED_NSE_CLOSE"})
        return {"source": "NSE official CM-UDiFF daily bhavcopy",
                "collection_status": _state["status"], "stocks": result}

def signals():
    with _lock:
        history = {s: list(rows) for s, rows in _history.items()}
        state = dict(_state)
    today = date.today()
    return {"source":state["source"], "source_status":state["status"],
            "sessions_loaded":state["sessions"], "stocks":[evaluate(s, rows, as_of=today)
            for s, rows in history.items()]}

def collect(reference=None, max_calendar_days=130):
    reference = reference or date.today()
    with _lock:
        _state.update(status="LOADING", sessions=0, attempted=0, errors=0, latest_session=None)
    successes = 0
    for offset in range(max_calendar_days):
        day = reference - timedelta(days=offset)
        if day.weekday() >= 5:
            continue
        try:
            report = download_session(day)
        except Exception:
            with _lock:
                _state["errors"] += 1
                _state["attempted"] += 1
            continue
        with _lock:
            for symbol in RESEARCH_UNIVERSE:
                row = report.get(symbol)
                if row is not None and not any(old["date"] == row["date"] for old in _history[symbol]):
                    _history[symbol].append(row)
            _state["sessions"] += 1
            _state["attempted"] += 1
            if _state["latest_session"] is None:
                _state["latest_session"] = day.isoformat()
        successes += 1
        if successes % 15 == 0:
            _save_cache()
            print("NSE_HISTORY_PROGRESS:", successes, "verified sessions", flush=True)
        if successes >= 78:
            break
        time.sleep(0.12)
    with _lock:
        for symbol in _history:
            _history[symbol].sort(key=lambda row: row["date"])
        _state["status"] = "READY" if successes >= 70 else "INSUFFICIENT_HISTORY"
        print("NSE_HISTORY_RESULT:", dict(_state, stocks_with_70_sessions=sum(len(v)>=70 for v in _history.values()), insufficient_symbols=[{"symbol":s,"sessions":len(v)} for s,v in _history.items() if len(v)<70]), flush=True)
    _save_cache()

def start():
    _restore_cache()
    threading.Thread(target=collect, daemon=True, name="nse-history-collector").start()
