import sqlite3
import time
import os
import upstox_client
from .market_config import INDICES
from .stock_universe import NIFTY_200
from .candles import Candle
from .upstox_live import UpstoxLiveV3
from .candle_manager import CandleManager
from .indicators import ema, momentum, atr
from .signal_engine import generate_signal
from .market_regime import index_signal
from .trade_engine import buy, update_state, sell
from .database import DB_PATH, init_db, reset_scanner_results

candles = CandleManager()
active_trades = {}
instrument_symbols = {key: symbol for symbol, key in {**NIFTY_200, **INDICES}.items()}
market_regimes = {}
previous_closes = {}
last_trade_updates = {}
last_cumulative_volumes = {}


def load_active_trades():
    active_trades.clear()
    con = sqlite3.connect(DB_PATH)
    rows = con.execute("SELECT id,symbol,target_1,target_2,invalidation,status FROM trades WHERE status NOT IN ('SELL','CLOSED')").fetchall()
    con.close()
    for trade_id, symbol, t1, t2, invalidation, status in rows:
        active_trades[symbol] = {"id": trade_id, "target_1": t1, "target_2": t2, "invalidation": invalidation, "status": status}
    print("ACTIVE TRADE CACHE:", len(active_trades))

def close_stale_trades():
    con = sqlite3.connect(DB_PATH)
    con.execute("""UPDATE trades SET status='CLOSED', exit_reason='Session reset', exit_time=datetime('now','+5 hours','+30 minutes'), exit_price=current_price, realized_pnl=current_price-entry_price, realized_pnl_pct=((current_price-entry_price)/entry_price)*100 WHERE status NOT IN ('CLOSED','SELL') AND date(signal_time) < date('now','+5 hours','+30 minutes')""")
    con.commit()
    con.close()

    try:
        from .postgres_history import save_completed_trades
        save_completed_trades()
    except Exception as exc:
        print(f"PostgreSQL session-reset history sync failed: {exc}")


def preload_history(key):
    config = upstox_client.Configuration()
    config.access_token = os.environ["UPSTOX_ACCESS_TOKEN"]
    api = upstox_client.HistoryV3Api(upstox_client.ApiClient(config))

    from datetime import datetime, timedelta
    from zoneinfo import ZoneInfo

    today = datetime.now(ZoneInfo("Asia/Kolkata")).date()
    to_date = today - timedelta(days=1)
    from_date = to_date - timedelta(days=7)

    response = api.get_historical_candle_data1(
        key, "minutes", "1",
        str(to_date), str(from_date)
    )
    rows = response.data.candles or []

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

    if key in INDICES.values() and loaded:
        previous_closes[key] = loaded[-1].close

    if key in INDICES.values():
        intraday = api.get_intra_day_candle_data(key, "minutes", "1")
        today_rows = intraday.data.candles or []
        current = []
        for row in reversed(today_rows):
            c = Candle(float(row[1]), float(row[5]))
            c.open, c.high, c.low, c.close = map(float, row[1:5])
            c.timestamp = datetime.fromisoformat(row[0]).astimezone(ZoneInfo("Asia/Kolkata")).replace(tzinfo=None)
            current.append(c)
        if current:
            loaded = current
            print("INTRADAY PRELOAD:", key, len(current), "candles")

    candles.completed[key] = loaded
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
        if len(group) == 5:
            complete.append(group)

    if len(complete) < 3:
        return "NEUTRAL"

    closes = [group[-1].close for group in complete[-3:]]

    if closes[0] < closes[1] < closes[2]:
        return "BULLISH"
    if closes[0] > closes[1] > closes[2]:
        return "BEARISH"
    return "NEUTRAL"

def save_scan_result(key, price, ema9_value, ema20_value, mom, market, trend_5m, signal, previous_close=None):
    candle_time = next((items[-1].timestamp.strftime('%Y-%m-%d %H:%M:%S') for instrument, items in candles.completed.items() if instrument_symbols.get(instrument, instrument) == key and items), None)
    con = sqlite3.connect(DB_PATH)
    con.execute("""INSERT OR REPLACE INTO scanner_results (symbol,updated_at,price,ema9,ema20,momentum,market,trend_5m,signal,previous_close) VALUES (?,?,?,?,?,?,?,?,?,?)""", (key, candle_time, price, ema9_value, ema20_value, mom, market, trend_5m, signal, previous_close))
    con.commit()
    con.close()


def analyse(key):
    history = candles.completed.get(key, [])

    # EMA20 requires enough completed candles.
    if len(history) < 20:
        print("WARMUP:", key, len(history), "/20 candles")
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

    closes = [c.close for c in history]
    highs = [c.high for c in history]
    lows = [c.low for c in history]
    atr_value = atr(highs, lows, closes, 14)
    price = closes[-1]

    ema9 = ema(closes, 9)
    ema20 = ema(closes, 20)
    mom = momentum(closes)

    # Require genuine relative volume for NIFTY 200 stock BUY signals.
    # Indices and SELL signals retain their existing rules.
    vwap_value = None
    rvol = None
    if key in NIFTY_200.values():
        volumes = [float(c.volume) for c in history[-20:]]
        baseline = volumes[:-1]
        if len(baseline) == 19 and all(v >= 0 for v in volumes):
            average_volume = sum(baseline) / len(baseline)
            rvol = volumes[-1] / average_volume if average_volume > 0 else 0.0
        if rvol is None:
            rvol = 0.0

    market = index_signal(price, ema9, ema20, vwap_value)
    if key == INDICES["NIFTY 50"]:
        market_regimes["NIFTY 50"] = market
    elif key in NIFTY_200.values() or key in INDICES.values():
        market = market_regimes.get("NIFTY 50", "NEUTRAL")

    signal = generate_signal(
        price,
        ema9,
        ema20,
        vwap_value,
        mom,
        rvol,
        market,
    )

    trend_5m = five_minute_trend(history)

    if key in INDICES.values():
        if ema9 > ema20 and mom > 0:
            signal = "BUY"
        elif ema9 < ema20 and mom < 0:
            signal = "SELL"
        else:
            signal = "HOLD"
    elif signal == "BUY" and trend_5m != "BULLISH":
        signal = "HOLD"
    elif signal == "SELL" and trend_5m != "BEARISH":
        signal = "HOLD"

    # Avoid chasing an extended stock BUY entry.
    # Keep index and SELL signal rules unchanged.
    if (
        key in NIFTY_200.values()
        and signal == "BUY"
        and atr_value is not None
        and atr_value > 0
        and price > ema9 + (0.5 * atr_value)
    ):
        signal = "HOLD"
        print("LATE BUY REJECTED:", key, "| PRICE:", price, "| EMA9:", ema9, "| ATR:", atr_value)

    if key in NIFTY_200.values() or key in INDICES.values():
        save_scan_result(instrument_symbols.get(key, key), price, ema9, ema20, mom, market, trend_5m, signal, previous_closes.get(key))
    if key in NIFTY_200.values() and signal == "BUY" and atr_value is not None:
        buy(key, price, price + atr_value, price + (2 * atr_value), price - atr_value, "V2 momentum BUY")
        load_active_trades()

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
    ts = data.get("ltt") or int(time.time() * 1000)

    if price is None:
        return

    # Manage open trades from memory instead of querying SQLite every tick.
    trade = active_trades.get(key)
    if trade:
        trade_id = trade["id"]
        t1 = trade["target_1"]
        t2 = trade["target_2"]
        invalidation = trade["invalidation"]

        if price <= invalidation:
            sell(trade_id, price, "Invalidation hit")
            active_trades.pop(key, None)
        elif price >= t2:
            sell(trade_id, price, "Target 2 hit")
            active_trades.pop(key, None)
        elif price >= t1:
            if trade["status"] != "TARGET_1":
                trade["status"] = "TARGET_1"
                update_state(trade_id, price, "TARGET_1", "Target 1 hit")
                last_trade_updates[key] = time.time()
            elif time.time() - last_trade_updates.get(key, 0) >= 5:
                update_state(trade_id, price, "TARGET_1")
                last_trade_updates[key] = time.time()
        else:
            if time.time() - last_trade_updates.get(key, 0) >= 5:
                update_state(trade_id, price, trade["status"])
                last_trade_updates[key] = time.time()

    cumulative = data.get("vtt")
    minute_volume = 0
    if cumulative is not None:
        try:
            cumulative = int(float(cumulative))
            previous = last_cumulative_volumes.get(key)
            if previous is not None and cumulative >= previous:
                minute_volume = cumulative - previous
            last_cumulative_volumes[key] = cumulative
            if key in NIFTY_200.values() and previous is not None and cumulative > previous and not getattr(on_tick, "_volume_verified", False):
                print("VOLUME_VERIFIED:", key, "previous:", previous, "current:", cumulative, "minute_increment:", minute_volume, flush=True)
                on_tick._volume_verified = True
        except (ValueError, TypeError):
            pass

    before = len(candles.completed.get(key, []))
    candles.update(key, price, ts, minute_volume)
    after = len(candles.completed.get(key, []))

    # Analyse only when a minute candle has actually closed.
    if after > before:
        analyse(key)


if __name__ == "__main__":
    init_db()
    reset_scanner_results()
    close_stale_trades()

    try:
        from .postgres_history import restore_active_trades
        restore_active_trades()
    except Exception as exc:
        print(f"Active trade restoration failed: {exc}")

    load_active_trades()

    preload_keys = list(INDICES.values()) + list(NIFTY_200.values())

    for key in preload_keys:
        try:
            preload_history(key)
            time.sleep(0.15)
            loaded = len(candles.completed.get(key, []))

            if key == INDICES["NIFTY 50"] and loaded >= 20:
                closes = [c.close for c in candles.completed[key]]
                market_regimes["NIFTY 50"] = index_signal(closes[-1], ema(closes, 9), ema(closes, 20), None)
                print("INITIAL NIFTY 50 REGIME:", market_regimes["NIFTY 50"])

            if loaded >= 20:
                print("PRELOAD READY:", key, loaded, "/20 candles")
            else:
                print("PRELOAD: live candle warmup for", key, "starting at", loaded, "/20")

        except Exception as e:
            print("PRELOAD ERROR:", key, str(e))
            print("PRELOAD: live candle warmup for", key)

    for key in INDICES.values():
        if len(candles.completed.get(key, [])) >= 20:
            analyse(key)
    # Display last available index values before live candles arrive.
    # These are informational only; do not run trading analysis here.
    for key in INDICES.values():
        history = candles.completed.get(key, [])
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

    UpstoxLiveV3(on_tick=on_tick).connect()
