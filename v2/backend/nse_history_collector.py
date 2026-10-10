"""Read-only daily NSE historical collector with explicit progress and fail-closed signals.

The preview's in-memory cache resets on Render restarts. No trades are placed.
"""
import threading
import time
from datetime import date, timedelta
from v2.backend.nse_daily_source import download_session
from v2.backend.investment_watchlist_57 import RESEARCH_UNIVERSE
from v2.backend.verified_positional_signals import evaluate

_lock = threading.Lock()
_history = {s: [] for s in RESEARCH_UNIVERSE}
_state = {"status":"NOT_STARTED","sessions":0,"attempted":0,"errors":0,"latest_session":None,
          "source":"NSE official CM-UDiFF daily bhavcopy", "persistence":"in-memory only"}

def snapshot():
    with _lock:
        return dict(_state, stocks_with_70_sessions=sum(len(v)>=70 for v in _history.values()),
                    watchlist_count=len(RESEARCH_UNIVERSE),
                    insufficient_symbols=[{"symbol":s,"sessions":len(v)} for s,v in _history.items() if len(v)<70])

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
                if row is not None:
                    _history[symbol].append(row)
            _state["sessions"] += 1
            _state["attempted"] += 1
            if _state["latest_session"] is None:
                _state["latest_session"] = day.isoformat()
        successes += 1
        if successes % 15 == 0:
            print("NSE_HISTORY_PROGRESS:", successes, "verified sessions", flush=True)
        if successes >= 78:
            break
        time.sleep(0.12)
    with _lock:
        for symbol in _history:
            _history[symbol].sort(key=lambda row: row["date"])
        _state["status"] = "READY" if successes >= 70 else "INSUFFICIENT_HISTORY"
        print("NSE_HISTORY_RESULT:", dict(_state, stocks_with_70_sessions=sum(len(v)>=70 for v in _history.values()), insufficient_symbols=[{"symbol":s,"sessions":len(v)} for s,v in _history.items() if len(v)<70]), flush=True)

def start():
    threading.Thread(target=collect, daemon=True, name="nse-history-collector").start()
