import sqlite3
import time
import os
import math
import upstox_client
from .market_config import INDICES
from .stock_universe import NIFTY_200
from .candles import Candle
from .upstox_live import UpstoxLiveV3
from .candle_manager import CandleManager
from .gap_recovery_worker import GapRecoveryWorker
from .indicators import ema, momentum, atr
from .signal_engine import generate_signal
from .market_regime import index_signal
from .database import DB_PATH, init_db, reset_scanner_results
from .decision_learning import classify_market_recovery
from .offline_preload_selection import select_completed_preload
from .volume_metrics import (
    completed_intraday_bars, verified_same_slot_relative_volume,
    confirmed_range_breakout, compact_same_slot_volume_rows,
)
from .stock_setup_rules import (
    SetupConfig, evaluate_stock_setup, verified_previous_day_levels,
    wait_stock_setup,
)

def _log_process_memory(stage, instrument=None):
    """Emit low-overhead Linux RSS diagnostics to identify preload memory spikes."""
    try:
        values = {}
        with open("/proc/self/status", encoding="utf-8") as status:
            for line in status:
                if line.startswith(("VmRSS:", "VmHWM:")):
                    key, value = line.split(":", 1)
                    values[key.lower()] = int(value.strip().split()[0])
        print("PROCESS_MEMORY:", {
            "process": "scanner", "stage": stage, "instrument": instrument,
            "rss_kb": values.get("vmrss"), "peak_rss_kb": values.get("vmhwm"),
        }, flush=True)
    except (OSError, ValueError, IndexError) as exc:
        print("PROCESS_MEMORY_UNAVAILABLE:", "scanner", stage, type(exc).__name__, flush=True)


candles = CandleManager()

_recovery_worker = None


def fetch_recovery_rows(key):
    """Fetch Upstox intraday rows off the websocket callback thread."""
    config = upstox_client.Configuration()
    config.access_token = os.environ["UPSTOX_ACCESS_TOKEN"]
    api = upstox_client.HistoryV3Api(upstox_client.ApiClient(config))
    response = api.get_intra_day_candle_data(key, "minutes", "1")
    return response.data.candles or []


def configure_gap_recovery(*, enabled=False, fetch_rows=None):
    """Explicit opt-in after preload; production default stays disabled."""
    global _recovery_worker
    if not enabled:
        previous = _recovery_worker
        _recovery_worker = None
        if previous is not None:
            previous.close(timeout=5)
        return None
    if _recovery_worker is not None:
        return _recovery_worker
    _recovery_worker = GapRecoveryWorker(
        fetch_rows if fetch_rows is not None else fetch_recovery_rows,
        candles.snapshot,
        candles.merge_verified_recovery,
    )
    return _recovery_worker


def request_recovery_on_gap(key):
    """Enqueue only for an observed same-session missing minute."""
    worker = _recovery_worker
    if worker is None:
        return False
    history, active = candles.snapshot(key)
    if active is None or not history:
        return False
    latest = history[-1].timestamp
    if latest.date() != active.date() or latest >= active:
        return False
    from datetime import timedelta
    # A missing completed minute lies between the last closed candle and
    # the newly active minute. Earlier history gaps also matter, but must not
    # repeatedly trigger requests once this boundary is contiguous.
    if active - latest <= timedelta(minutes=1):
        return False
    return worker.request(key)

instrument_symbols = {key: symbol for symbol, key in {**NIFTY_200, **INDICES}.items()}
market_regimes = {}
previous_closes = {}
_index_recovery_state = {}
last_cumulative_volumes = {}
historical_5m_volume = {}
previous_day_levels = {}
stock_setup_states = {}

_tick_seen = {}
_last_accepted_tick_ms = {}
_last_health_write = 0.0
_HEALTH_PATH = "/tmp/nse_200_feed_health.json"


def update_market_recovery(key, price, tick_time):
    """Track large index drops and recovery from verified session lows."""
    if key not in INDICES.values():
        return None
    previous_close = previous_closes.get(key)
    history, _ = candles.snapshot(key)
    session_day = tick_time.date()
    today = [c for c in history if getattr(c, "timestamp", None) is not None
             and c.timestamp.date() == session_day]
    low_candidates = [float(c.low) for c in today]
    low_candidates.append(float(price))
    session_low = min(low_candidates)
    highs = [float(c.high) for c in today[-20:]]
    lows = [float(c.low) for c in today[-20:]]
    closes = [float(c.close) for c in today[-20:]]
    index_atr = atr(highs, lows, closes, 14) if len(closes) >= 14 else None

    prior = _index_recovery_state.get(key, {})
    if prior.get("session_date") != session_day.isoformat():
        prior_fraction = 0.0
    else:
        prior_fraction = prior.get("max_recovery_fraction", 0.0)
    index_name = instrument_symbols.get(key, key)
    classification = classify_market_recovery(
        previous_close,
        session_low,
        price,
        index_atr,
        prior_recovery_fraction=prior_fraction,
        trend=market_regimes.get("NIFTY 50") if index_name != "NIFTY 50" else market_regimes.get(index_name),
        # Index VWAP is not yet verified by this feed; do not claim confirmation.
        above_vwap=None,
    )
    fraction = classification.get("recovery_fraction", 0.0)
    _index_recovery_state[key] = {
        "session_date": session_day.isoformat(),
        "max_recovery_fraction": max(prior_fraction, fraction or 0.0),
        "observed_at_ist": tick_time.isoformat(),
        "source": "accepted_live_tick_and_completed_candles",
        "classification": classification,
    }
    return classification


def market_recovery_context(asof=None):
    from datetime import datetime, timedelta
    from zoneinfo import ZoneInfo

    asof = asof or datetime.now(ZoneInfo("Asia/Kolkata"))
    names = ("NIFTY 50", "SENSEX", "BANK NIFTY")
    result = {}
    for name in names:
        key = INDICES.get(name)
        state = _index_recovery_state.get(key, {}) if key else {}
        observed = state.get("observed_at_ist")
        if observed:
            try:
                stamp = datetime.fromisoformat(observed)
                if stamp.tzinfo is None:
                    stamp = stamp.replace(tzinfo=ZoneInfo("Asia/Kolkata"))
                fresh = timedelta(0) <= asof - stamp <= timedelta(seconds=120)
            except ValueError:
                fresh = False
        else:
            fresh = False
        result[name] = (dict(state.get("classification", {"status": "UNAVAILABLE"}))
                        if fresh else {"status": "UNAVAILABLE"})
        result[name]["feed_fresh"] = fresh
        if observed:
            result[name]["observed_at_ist"] = observed
            result[name]["source"] = state["source"]
    return result


def _decision_context(symbol, price, decision_time, *, features=None):
    return {
        "schema_version": 1,
        "decision_time_ist": decision_time.isoformat() if decision_time else None,
        "symbol": instrument_symbols.get(symbol, symbol),
        "price": float(price) if price is not None else None,
        "market_regime": market_regimes.get("NIFTY 50", "UNAVAILABLE"),
        "market_recovery": market_recovery_context(decision_time),
        "features": features or {},
    }

def record_feed_health(key):
    global _last_health_write
    if key not in NIFTY_200.values():
        return
    now = time.time()
    _tick_seen[key] = now
    if now - _last_health_write < 10:
        return
    import json
    from datetime import datetime
    from zoneinfo import ZoneInfo
    from pathlib import Path
    _last_health_write = now
    try:
        path = Path(_HEALTH_PATH)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps({
            "observed_at_ist": datetime.now(ZoneInfo("Asia/Kolkata")).isoformat(),
            "observed_at_epoch": now,
            "last_tick_epoch": _tick_seen,
        }))
        tmp.replace(path)
    except OSError as exc:
        print("FEED_HEALTH_WRITE_ERROR:", type(exc).__name__, flush=True)



_last_quality_write = 0.0
_QUALITY_PATH = "/tmp/nse_200_candle_quality.json"

def write_candle_quality():
    """Publish observed completed-candle quality; never infer missing bars."""
    global _last_quality_write
    now = time.time()
    if now - _last_quality_write < 10:
        return
    _last_quality_write = now
    import json
    from pathlib import Path
    from datetime import datetime, timedelta
    from zoneinfo import ZoneInfo
    today = datetime.now(ZoneInfo("Asia/Kolkata")).date()
    rows = {}
    for key in NIFTY_200.values():
        history, _ = candles.snapshot(key)
        recent = history[-6:]
        same_day = len(recent) == 6 and all(
            getattr(c, "timestamp", None) is not None
            and c.timestamp.date() == today for c in recent
        )
        consecutive = same_day and all(
            recent[i].timestamp - recent[i-1].timestamp == timedelta(minutes=1)
            for i in range(1, 6)
        )
        last = history[-1] if history else None
        if len(recent) < 6:
            reason = "WARMUP"
        elif not same_day:
            reason = "OVERNIGHT_GAP"
        elif not consecutive:
            reason = "MISSING_MINUTE"
        else:
            reason = None
        rows[instrument_symbols.get(key, key)] = {
            "six_consecutive_today": consecutive,
            "continuity_reason": reason,
            "last_closed_candle_ist": last.timestamp.isoformat() if last else None,
            "last_closed_volume": float(last.volume) if last else None,
            "last_tick_epoch": _tick_seen.get(key),
        }
    try:
        path = Path(_QUALITY_PATH)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps({"observed_at_epoch": now, "stocks": rows}))
        tmp.replace(path)
    except (OSError, TypeError, ValueError) as exc:
        print("CANDLE_QUALITY_WRITE_ERROR:", type(exc).__name__, flush=True)


def preload_history(key):
    config = upstox_client.Configuration()
    config.access_token = os.environ["UPSTOX_ACCESS_TOKEN"]
    api = upstox_client.HistoryV3Api(upstox_client.ApiClient(config))

    from datetime import datetime, timedelta
    from zoneinfo import ZoneInfo

    today = datetime.now(ZoneInfo("Asia/Kolkata")).date()
    to_date = today - timedelta(days=1)
    from_date = to_date - timedelta(days=7)

    # One five-minute historical request per stock per scanner start supplies
    # the same-slot 20-session RVOL baseline used by stock setup rules.
    if key in NIFTY_200.values():
        try:
            volume_from_date = to_date - timedelta(days=29)
            volume_response = api.get_historical_candle_data1(
                key, "minutes", "5", str(to_date), str(volume_from_date)
            )
            historical_5m_volume[key] = compact_same_slot_volume_rows(
                volume_response.data.candles or [], reference_sessions=20
            )
            del volume_response
            print("5M VOLUME BASELINE:", key, historical_5m_volume[key].row_count,
                  "compact rows", flush=True)
        except Exception as exc:
            historical_5m_volume[key] = []
            print("5M VOLUME BASELINE UNAVAILABLE:", key, type(exc).__name__, flush=True)
        finally:
            # Do not retain a full SDK response while fetching 1-minute data.
            if "volume_response" in locals():
                del volume_response
        _log_process_memory("after_5m_volume_baseline", key)

    response = api.get_historical_candle_data1(
        key, "minutes", "1",
        str(to_date), str(from_date)
    )
    rows = response.data.candles or []

    if key in NIFTY_200.values():
        previous_day_levels[key] = verified_previous_day_levels(rows, today) or {}

    if not rows:
        print("PRELOAD: no historical candles for", key)
        return

    loaded = []
    for row in reversed(rows[:20]):
        c = Candle(float(row[1]), float(row[5]))
        c.open = float(row[1])
        c.high = float(row[2])
        c.low = float(row[3])
        c.close = float(row[4])
        c.timestamp = datetime.fromisoformat(row[0]).astimezone(ZoneInfo("Asia/Kolkata")).replace(tzinfo=None)
        loaded.append(c)
    del rows

    if key in INDICES.values() and loaded:
        previous_closes[key] = loaded[-1].close

    # Warm stocks as well as indices with today's *completed* intraday bars.
    # Keep previous-day data only as an indicator warmup fallback. Never preload
    # the still-forming current minute, and never treat an API error as valid data.
    if key in INDICES.values() or key in NIFTY_200.values():
        try:
            intraday = api.get_intra_day_candle_data(key, "minutes", "1")
            today_rows = intraday.data.candles or []
            now_ist = datetime.now(ZoneInfo("Asia/Kolkata")).replace(tzinfo=None)
            current_minute = now_ist.replace(second=0, microsecond=0)
            current = []
            seen_minutes = set()
            for row in today_rows:
                stamp = datetime.fromisoformat(row[0]).astimezone(
                    ZoneInfo("Asia/Kolkata")
                ).replace(tzinfo=None)
                if stamp.date() != today or stamp >= current_minute or stamp in seen_minutes:
                    continue
                seen_minutes.add(stamp)
                c = Candle(float(row[1]), float(row[5]))
                c.open, c.high, c.low, c.close = map(float, row[1:5])
                c.timestamp = stamp
                current.append(c)
            current.sort(key=lambda c: c.timestamp)
            # Preserve the full completed session so EMA initialization remains
            # stable across scanner restarts; the manager has no active cap.
            loaded = select_completed_preload(
                loaded, current, session_date=today, current_minute=current_minute
            )
            del today_rows, current, seen_minutes
            print("INTRADAY PRELOAD:", key, len(loaded), "completed candles", flush=True)
        except Exception as exc:
            print("INTRADAY PRELOAD FAILED:", key, type(exc).__name__, flush=True)

    candles.preload_completed(key, loaded)
    _log_process_memory("after_intraday_preload", key)
    print("PRELOAD:", key, len(loaded), "historical candles")

def five_minute_trend(history):
    timed = [c for c in history if hasattr(c, "timestamp")]
    if timed:
        session_date = timed[-1].timestamp.date()
        timed = [c for c in timed if c.timestamp.date() == session_date]
    if len(timed) < 15:
        return "NEUTRAL"

    buckets = {}
    for c in timed:
        ts = c.timestamp
        bucket = ts.replace(minute=(ts.minute // 5) * 5, second=0, microsecond=0)
        buckets.setdefault(bucket, []).append(c)

    complete = []
    for bucket in sorted(buckets):
        group = buckets[bucket]
        # A 5-minute reading is valid only when all five consecutive minute
        # closes are present. Partial or duplicated intervals are ignored.
        if len(group) == 5 and all(
            (group[i].timestamp - group[i - 1].timestamp).total_seconds() == 60
            for i in range(1, 5)
        ):
            complete.append(group)

    if len(complete) < 3:
        return "NEUTRAL"

    latest_groups = complete[-3:]
    if any(
        (latest_groups[i][0].timestamp - latest_groups[i - 1][0].timestamp).total_seconds() != 300
        for i in range(1, 3)
    ):
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
    session_date = timed[-1].timestamp.date()
    timed = [c for c in timed if c.timestamp.date() == session_date]
    buckets = {}
    for candle in timed:
        ts = candle.timestamp
        bucket = ts.replace(minute=(ts.minute // 5) * 5, second=0, microsecond=0)
        buckets.setdefault(bucket, []).append(candle)
    complete = []
    for bucket in sorted(buckets):
        group = buckets[bucket]
        if len(group) == 5 and all(
            (group[i].timestamp - group[i - 1].timestamp).total_seconds() == 60
            for i in range(1, 5)
        ):
            complete.append(group)
    if len(complete) < 4:
        return False
    last_four = complete[-4:]
    if any(
        (last_four[i][0].timestamp - last_four[i - 1][0].timestamp).total_seconds() != 300
        for i in range(1, 4)
    ):
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
    buffer = max(latest_close * 0.001, 0.25 * (sum(prior_ranges) / len(prior_ranges)))
    if direction == "BUY":
        return latest_close > prior_high + buffer
    if direction == "SELL":
        return latest_close < prior_low - buffer
    return False

def completed_candle_time_for_symbol(symbol):
    """Read the latest completed minute for a displayed symbol under lock."""
    for instrument, display_symbol in instrument_symbols.items():
        if display_symbol != symbol:
            continue
        history, _ = candles.snapshot(instrument)
        if history:
            return history[-1].timestamp.strftime('%Y-%m-%d %H:%M:%S')
    return None


def save_scan_result(key, price, ema9_value, ema20_value, mom, market, trend_5m, signal, previous_close=None, rvol=None, current_volume=None, baseline_volume=None, volume_candle_time=None):
    candle_time = completed_candle_time_for_symbol(key)
    con = sqlite3.connect(DB_PATH)
    con.execute("""INSERT OR REPLACE INTO scanner_results
        (symbol,updated_at,price,ema9,ema20,momentum,market,trend_5m,signal,
         previous_close,rvol,current_volume,baseline_volume,volume_candle_at)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (key, candle_time, price, ema9_value, ema20_value, mom, market,
         trend_5m, signal, previous_close, rvol, current_volume, baseline_volume,
         volume_candle_time))
    if candle_time is not None:
        con.execute("""INSERT OR REPLACE INTO scanner_signal_history
            (symbol,candle_time,price,ema9,ema20,momentum,market,trend_5m,signal)
            VALUES (?,?,?,?,?,?,?,?,?)""",
            (key,candle_time,price,ema9_value,ema20_value,mom,market,trend_5m,signal))
    con.commit()
    con.close()
    if key in ("NIFTY 50", "SENSEX") and candle_time is not None:
        try:
            from .index_snapshot_archive import save_index_snapshot
            save_index_snapshot(key, candle_time, price)
        except Exception as exc:
            print(f"Index snapshot archive unavailable: {type(exc).__name__}", flush=True)


def save_stock_setup(setup):
    import json
    from datetime import datetime
    from zoneinfo import ZoneInfo
    symbol = setup.get("symbol")
    if symbol not in NIFTY_200:
        return
    now = datetime.now(ZoneInfo("Asia/Kolkata")).isoformat()
    try:
        with sqlite3.connect(DB_PATH, timeout=5) as con:
            con.execute("""INSERT INTO scanner_stock_setups(symbol,updated_at,setup_json)
                VALUES(?,?,?) ON CONFLICT(symbol) DO UPDATE SET
                updated_at=excluded.updated_at, setup_json=excluded.setup_json""",
                (symbol, now, json.dumps(setup, separators=(",", ":"), allow_nan=False)))
    except (sqlite3.Error, TypeError, ValueError) as exc:
        print("STOCK_SETUP_PERSIST_FAILED:", symbol, type(exc).__name__, flush=True)


def load_stock_setup_states():
    import json
    try:
        with sqlite3.connect(DB_PATH, timeout=5) as con:
            rows = con.execute("SELECT symbol,setup_json FROM scanner_stock_setups").fetchall()
        for symbol, payload in rows:
            if symbol in NIFTY_200:
                setup = json.loads(payload)
                if isinstance(setup, dict):
                    stock_setup_states[NIFTY_200[symbol]] = setup
    except (sqlite3.Error, ValueError, TypeError):
        return


def persist_stock_setup_wait(key, reason, history):
    """Persist a per-stock data-quality blocker instead of leaving an empty row."""
    if key not in NIFTY_200.values():
        return
    latest = history[-1] if history else None
    stamp = getattr(latest, "timestamp", None)
    setup = wait_stock_setup(
        instrument_symbols.get(key, key), reason,
        last_observed_minute_candle_time=stamp.isoformat() if stamp else None,
    )
    stock_setup_states[key] = setup
    save_stock_setup(setup)


def analyse(key):
    history, _ = candles.snapshot(key)

    # Reject old candles before generating any signals.
    if history:
        from datetime import datetime, timedelta
        from zoneinfo import ZoneInfo

        last_candle = history[-1].timestamp
        now_ist = datetime.now(ZoneInfo("Asia/Kolkata")).replace(tzinfo=None)

        if last_candle > now_ist or now_ist - last_candle > timedelta(minutes=3):
            print("STALE_CANDLE_BLOCKED:", key, flush=True)
            persist_stock_setup_wait(
                key, "WAIT: latest 1-minute candle is stale or future-dated", history
            )
            return

    # Measure signal processing delay without changing trading rules.
    if history and hasattr(history[-1], "timestamp"):
        from datetime import datetime, timedelta
        from zoneinfo import ZoneInfo

        candle_time = history[-1].timestamp
        expected_close = candle_time + timedelta(minutes=1)
        now_ist = datetime.now(ZoneInfo("Asia/Kolkata")).replace(tzinfo=None)

        if candle_time.date() == now_ist.date():
            delay_seconds = (now_ist - expected_close).total_seconds()
            if delay_seconds >= 0:
                print(
                    "SIGNAL_TIMING:",
                    key,
                    "| CANDLE:", candle_time,
                    "| DELAY_SECONDS:", round(delay_seconds, 1),
                    flush=True,
                )

    # EMA20 requires enough completed candles.
    if len(history) < 20:
        print("WARMUP:", key, len(history), "/20 candles")
        persist_stock_setup_wait(
            key, f"WAIT: scanner warm-up has {len(history)}/20 completed 1-minute candles",
            history,
        )
        return

    if key in INDICES.values():
        from datetime import datetime
        from zoneinfo import ZoneInfo
        today = datetime.now(ZoneInfo("Asia/Kolkata")).date()
        history = [
            c for c in history
            if hasattr(c, "timestamp") and c.timestamp.date() == today
        ]
        if len(history) < 20:
            return

    # Five-bar momentum must never bridge overnight or a missing 1-minute bar.
    # Historical warmup is allowed for EMA/ATR, but the latest six closes
    # used for momentum must be from consecutive minutes in today's session.
    from datetime import datetime, timedelta
    from zoneinfo import ZoneInfo
    today_ist = datetime.now(ZoneInfo("Asia/Kolkata")).date()
    recent = history[-6:]
    if len(recent) < 6:
        continuity_reason = "WARMUP"
    elif any(not hasattr(c, "timestamp") or c.timestamp.date() != today_ist for c in recent):
        continuity_reason = "OVERNIGHT_GAP"
    elif any(
        recent[i].timestamp - recent[i - 1].timestamp != timedelta(minutes=1)
        for i in range(1, len(recent))
    ):
        continuity_reason = "MISSING_MINUTE"
    else:
        continuity_reason = None
    if continuity_reason and key not in NIFTY_200.values():
        print(
            "MOMENTUM_CONTINUITY_BLOCKED:", key,
            "| REASON:", continuity_reason,
            "| LAST_SIX:", [
                getattr(c, "timestamp", None).strftime("%Y-%m-%d %H:%M")
                if getattr(c, "timestamp", None) is not None else "NO_TIMESTAMP"
                for c in recent
            ],
            flush=True,
        )
        persist_stock_setup_wait(
            key, f"WAIT: 1-minute candle continuity is {continuity_reason}; require six consecutive completed bars",
            history,
        )
        return

    if continuity_reason:
        # The legacy momentum path needs six consecutive 1-minute candles,
        # but the read-only stock setup engine uses separately aggregated,
        # completed and contiguous 5-minute bars. Let it evaluate that data
        # below; a 1-minute gap must not suppress a valid 5-minute setup.
        print(
            "MOMENTUM_CONTINUITY_NOT_REQUIRED_FOR_5M_SETUP:", key,
            "| REASON:", continuity_reason,
            "| LAST_SIX:", [
                getattr(c, "timestamp", None).strftime("%Y-%m-%d %H:%M")
                if getattr(c, "timestamp", None) is not None else "NO_TIMESTAMP"
                for c in recent
            ],
            flush=True,
        )

    closes = [c.close for c in history]
    highs = [c.high for c in history]
    lows = [c.low for c in history]
    atr_value = atr(highs, lows, closes, 14)
    price = closes[-1]

    ema9 = ema(closes, 9)
    ema20 = ema(closes, 20)
    mom = momentum(closes)

    # Stock setups use completed five-minute candles, verified levels and the
    # historical mean for the same 5-minute slot across 20 sessions.
    vwap_value = None
    rvol = None
    current_volume = None
    baseline_volume = None
    rvol_available = False
    bars_5m_all = (completed_intraday_bars(history, 5, include_all_sessions=True)
                   if key in NIFTY_200.values() else [])
    session_date = history[-1].timestamp.date() if history else None
    bars_5m = [bar for bar in bars_5m_all if bar["timestamp"].date() == session_date]
    current_5m = bars_5m[-1] if bars_5m else None
    if current_5m is not None:
        from datetime import timedelta
        latest_minute_end = history[-1].timestamp + timedelta(minutes=1)
        current_5m_end = current_5m["timestamp"] + timedelta(minutes=5)
        age = latest_minute_end - current_5m_end
        if age < timedelta(0) or age >= timedelta(minutes=5):
            current_5m = None
    volume_stats_5m = (
        verified_same_slot_relative_volume(
            current_5m, historical_5m_volume.get(key, ()),
            reference_sessions=20
        )
        if current_5m is not None else None
    )
    if volume_stats_5m is not None:
        rvol = volume_stats_5m["relative_volume"]
        current_volume = volume_stats_5m["current_volume"]
        baseline_volume = volume_stats_5m["baseline_volume"]
        rvol_available = True
    market = index_signal(price, ema9, ema20, vwap_value)
    if key == INDICES["NIFTY 50"]:
        market_regimes["NIFTY 50"] = market
    elif key in NIFTY_200.values() or key in INDICES.values():
        market = market_regimes.get("NIFTY 50", "NEUTRAL")

    trend_5m = five_minute_trend(history)
    setup = None
    if key in NIFTY_200.values():
        from datetime import datetime
        from zoneinfo import ZoneInfo
        now_ist = datetime.now(ZoneInfo("Asia/Kolkata")).replace(tzinfo=None)
        # Refresh levels from verified completed local history each session.
        # This avoids carrying yesterday's PDH/PDL forward after a long-running
        # service crosses the market date without a restart.
        previous_day_levels[key] = verified_previous_day_levels(
            [[c.timestamp.isoformat(), c.open, c.high, c.low, c.close, c.volume]
             for c in history], now_ist.date()
        ) or {}
        setup = evaluate_stock_setup(
            instrument_symbols.get(key, key), bars_5m, historical_5m_volume.get(key, ()),
            previous_day_levels.get(key, {}), now=now_ist, ema9=ema9, ema20=ema20,
            previous_state=stock_setup_states.get(key), config=SetupConfig.from_env(),
        )
        stock_setup_states[key] = setup
        save_stock_setup(setup)
        signal = ("BUY" if setup["status"] == "CONFIRMED" and setup["direction"] == "LONG"
                  else "SELL" if setup["status"] == "CONFIRMED" and setup["direction"] == "SHORT"
                  else "HOLD")
    else:
        signal = generate_signal(price, ema9, ema20, vwap_value, mom, rvol, market)
        if signal in ("BUY", "SELL") and (trend_5m != ("BULLISH" if signal == "BUY" else "BEARISH")
                                           or not five_minute_breakout(history, signal)):
            signal = "HOLD"

    if key in NIFTY_200.values() or key in INDICES.values():
        save_scan_result(
            instrument_symbols.get(key, key), price, ema9, ema20, mom,
            market, trend_5m, signal, previous_closes.get(key),
            rvol if rvol_available else None, current_volume, baseline_volume,
            current_5m["timestamp"].strftime("%Y-%m-%d %H:%M:%S")
            if current_5m is not None else None,
        )

    print(
        "SIGNAL:",
        key,
        "| PRICE:", price,
        "| EMA9:", ema9,
        "| EMA20:", ema20,
        "| MOM:", mom,
        "| RVOL:", round(rvol, 2) if rvol is not None else "N/A",
        "| MARKET:", market,
        "| 5M TREND:", trend_5m,
        "| SIGNAL:", signal,
    )


def on_tick(key, data):
    price = data.get("ltp")
    ts = data.get("ltt")
    if price is None or ts is None:
        return

    # Validate prices before touching an active position. NaN, infinity,
    # non-numeric and non-positive values must not reach trade or candle state.
    try:
        price = float(price)
        if not math.isfinite(price) or price <= 0:
            return
    except (TypeError, ValueError, OverflowError):
        return

    # Reject delayed, future-dated and malformed exchange ticks before they
    # affect scalper candles, volume, trade state or feed-health counters.
    try:
        ts = int(float(ts))
        now_ms = int(time.time() * 1000)
        if ts < 10**11:
            ts *= 1000  # Support Unix seconds as well as milliseconds.
        if ts > now_ms + 5000 or now_ms - ts > 120000:
            return
    except (TypeError, ValueError, OverflowError):
        return

    # Reject out-of-order exchange ticks within the same minute as well.
    # Otherwise a delayed tick can corrupt OHLC, cumulative-volume deltas,
    # and simulated trade state even when its minute is not older.
    last_accepted = _last_accepted_tick_ms.get(key)
    if last_accepted is not None and ts < last_accepted:
        return
    _last_accepted_tick_ms[key] = ts

    from datetime import datetime
    from zoneinfo import ZoneInfo
    tick_time = datetime.fromtimestamp(ts / 1000.0, ZoneInfo("Asia/Kolkata"))
    if key in INDICES.values():
        try:
            update_market_recovery(key, price, tick_time)
        except (TypeError, ValueError, OverflowError) as exc:
            print("MARKET_RECOVERY_CONTEXT_SKIPPED:", type(exc).__name__, flush=True)

    record_feed_health(key)

    cumulative = data.get("vtt")
    minute_volume = 0
    if cumulative is not None:
        try:
            volume_value = float(cumulative)
            if not math.isfinite(volume_value) or volume_value < 0:
                raise ValueError("invalid cumulative volume")
            cumulative = int(volume_value)
            previous = last_cumulative_volumes.get(key)
            if previous is not None and cumulative >= previous:
                minute_volume = cumulative - previous
            last_cumulative_volumes[key] = cumulative
            if key in NIFTY_200.values() and previous is not None and cumulative > previous and not getattr(on_tick, "_volume_verified", False):
                print("VOLUME_VERIFIED:", key, "previous:", previous, "current:", cumulative, "minute_increment:", minute_volume, flush=True)
                on_tick._volume_verified = True
        except (ValueError, TypeError, OverflowError):
            pass

    closed = candles.update(key, price, ts, minute_volume)

    # Only a live rollover may trigger decisions. Recovery can grow completed
    # history without closing the active candle.
    if closed is not None:
        request_recovery_on_gap(key)
        write_candle_quality()
        analyse(key)


def publish_preloaded_price(key):
    """Publish real completed history immediately, with no live trade signal."""
    if key not in INDICES.values() and key not in NIFTY_200.values():
        return
    history, _ = candles.snapshot(key)
    if len(history) < 20:
        return
    closes = [item.close for item in history]
    is_index = key in INDICES.values()
    save_scan_result(
        instrument_symbols.get(key, key), closes[-1],
        ema(closes, 9), ema(closes, 20), momentum(closes),
        "PREVIOUS SESSION" if is_index else "HISTORICAL_PRELOAD",
        None if is_index else five_minute_trend(history), "WAITING",
        previous_closes.get(key) if is_index else None,
    )


if __name__ == "__main__":
    init_db()
    load_stock_setup_states()
    reset_scanner_results()

    preload_keys = list(INDICES.values()) + list(NIFTY_200.values())
    _log_process_memory("before_all_preloads")

    for key in preload_keys:
        try:
            preload_history(key)
            time.sleep(0.15)
            loaded = len(candles.snapshot(key)[0])

            if key == INDICES["NIFTY 50"] and loaded >= 20:
                closes = [c.close for c in candles.snapshot(key)[0]]
                market_regimes["NIFTY 50"] = index_signal(closes[-1], ema(closes, 9), ema(closes, 20), None)
                print("INITIAL NIFTY 50 REGIME:", market_regimes["NIFTY 50"])

            publish_preloaded_price(key)

            if loaded >= 20:
                print("PRELOAD READY:", key, loaded, "/20 candles")
            else:
                print("PRELOAD: live candle warmup for", key, "starting at", loaded, "/20")

        except Exception as e:
            print("PRELOAD ERROR:", key, str(e))
            print("PRELOAD: live candle warmup for", key)

    for key in INDICES.values():
        if len(candles.snapshot(key)[0]) >= 20:
            analyse(key)
    # Display last available index values before live candles arrive.
    # These are informational only; do not run trading analysis here.
    for key in INDICES.values():
        history, _ = candles.snapshot(key)
        if len(history) >= 20:
            closes = [c.close for c in history]
            save_scan_result(
                instrument_symbols.get(key, key),
                closes[-1],
                ema(closes, 9),
                ema(closes, 20),
                momentum(closes),
                "PREVIOUS SESSION",
                None,
                "WAITING",
                previous_closes.get(key),
            )

    # Double opt-in: never turn recovery on in existing production settings.
    # Staging operator must explicitly set both values.
    recovery_enabled = (
        os.environ.get("NSE_RECOVERY_MODE") == "staging"
        and os.environ.get("NSE_ENABLE_VERIFIED_GAP_RECOVERY") == "1"
    )
    configure_gap_recovery(enabled=recovery_enabled)
    print("VERIFIED_GAP_RECOVERY:", "ENABLED_STAGING" if recovery_enabled else "DISABLED", flush=True)
    try:
        UpstoxLiveV3(on_tick=on_tick).connect()
    finally:
        # A bounded shutdown wait prevents abandoning an in-flight recovery
        # thread during a normal scanner exit; never place this in on_tick.
        worker = _recovery_worker
        if worker is not None:
            worker.close(timeout=5)

