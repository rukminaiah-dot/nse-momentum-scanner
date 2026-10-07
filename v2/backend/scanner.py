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
from .database import DB_PATH, init_db

candles = CandleManager()
active_trades = {}
instrument_symbols = {key: symbol for symbol, key in NIFTY_200.items()}
market_regimes = {}
last_trade_updates = {}


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

    candles.completed[key] = loaded
    print("PRELOAD:", key, len(loaded), "historical candles")

def five_minute_trend(history):
    timed = [c for c in history if hasattr(c, "timestamp")]
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

def save_scan_result(key, price, ema9_value, ema20_value, mom, market, trend_5m, signal):
    con = sqlite3.connect(DB_PATH)
    con.execute("""INSERT OR REPLACE INTO scanner_results (symbol,updated_at,price,ema9,ema20,momentum,market,trend_5m,signal) VALUES (?,datetime('now','+5 hours','+30 minutes'),?,?,?,?,?,?,?)""", (key, price, ema9_value, ema20_value, mom, market, trend_5m, signal))
    con.commit()
    con.close()


def analyse(key):
    history = candles.completed.get(key, [])

    # EMA20 requires enough completed candles.
    if len(history) < 20:
        print("WARMUP:", key, len(history), "/20 candles")
        return

    closes = [c.close for c in history]
    highs = [c.high for c in history]
    lows = [c.low for c in history]
    atr_value = atr(highs, lows, closes, 14)
    price = closes[-1]

    ema9 = ema(closes, 9)
    ema20 = ema(closes, 20)
    mom = momentum(closes)

    # Live Upstox LTPC feed currently has no candle volume.
    # Do not manufacture VWAP/RVOL values.
    vwap_value = None
    rvol = None

    market = index_signal(price, ema9, ema20, vwap_value)
    if key == INDICES["NIFTY 50"]:
        market_regimes["NIFTY 50"] = market
    elif key in NIFTY_200.values():
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

    if signal == "BUY" and trend_5m != "BULLISH":
        signal = "HOLD"
    elif signal == "SELL" and trend_5m != "BEARISH":
        signal = "HOLD"

    if key in NIFTY_200.values():
        save_scan_result(instrument_symbols.get(key, key), price, ema9, ema20, mom, market, trend_5m, signal)
    if signal == "BUY" and atr_value is not None:
        buy(key, price, price + atr_value, price + (2 * atr_value), price - atr_value, "V2 momentum BUY")
        load_active_trades()

    print(
        "SIGNAL:",
        key,
        "| PRICE:", price,
        "| EMA9:", ema9,
        "| EMA20:", ema20,
        "| MOM:", mom,
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
            trade["status"] = "TARGET_1"
            update_state(trade_id, price, "TARGET_1", "Target 1 hit")
        else:
            if time.time() - last_trade_updates.get(key, 0) >= 5:
                update_state(trade_id, price, trade["status"])
                last_trade_updates[key] = time.time()

    before = len(candles.completed.get(key, []))
    candles.update(key, price, ts)
    after = len(candles.completed.get(key, []))

    # Analyse only when a minute candle has actually closed.
    if after > before:
        analyse(key)


if __name__ == "__main__":
    init_db()
    close_stale_trades()
    load_active_trades()

    preload_keys = list(INDICES.values()) + list(NIFTY_200.values())

    for key in preload_keys:
        try:
            preload_history(key)
            time.sleep(0.15)
            loaded = len(candles.completed.get(key, []))

            if loaded >= 20:
                print("PRELOAD READY:", key, loaded, "/20 candles")
            else:
                print("PRELOAD: live candle warmup for", key, "starting at", loaded, "/20")

        except Exception as e:
            print("PRELOAD ERROR:", key, str(e))
            print("PRELOAD: live candle warmup for", key)

    UpstoxLiveV3(on_tick=on_tick).connect()
