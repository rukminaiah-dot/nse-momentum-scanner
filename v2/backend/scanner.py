import sqlite3
import time
import os
import upstox_client
from .market_config import INDICES
from .candles import Candle
from .upstox_live import UpstoxLiveV3
from .candle_manager import CandleManager
from .indicators import ema, momentum, atr
from .signal_engine import generate_signal
from .market_regime import index_signal
from .trade_engine import buy, update_state, sell
from .database import DB_PATH

candles = CandleManager()


def preload_history(key):
    config = upstox_client.Configuration()
    config.access_token = os.environ["UPSTOX_ACCESS_TOKEN"]
    api = upstox_client.HistoryV3Api(upstox_client.ApiClient(config))
    response = api.get_intra_day_candle_data(key, "minutes", 1)
    rows = response.data.candles

    loaded = []
    for row in reversed(rows[:20]):
        c = Candle(float(row[4]), 0)
        loaded.append(c)

    candles.completed[key] = loaded
    print("PRELOAD:", key, len(loaded), "candles")


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

    signal = generate_signal(
        price,
        ema9,
        ema20,
        vwap_value,
        mom,
        rvol,
        market,
    )

    if signal == "BUY" and atr_value is not None:
        buy(key, price, price + atr_value, price + (2 * atr_value), price - atr_value, "V2 momentum BUY")

    con = sqlite3.connect(DB_PATH)
    row = con.execute("SELECT id,target_1,target_2,invalidation FROM trades WHERE symbol=? AND status NOT IN ('SELL','CLOSED') ORDER BY id DESC LIMIT 1", (key,)).fetchone()
    con.close()
    if row:
        trade_id, t1, t2, invalidation = row
        if price <= invalidation:
            sell(trade_id, price, "Invalidation hit")
        elif price >= t2:
            sell(trade_id, price, "Target 2 hit")
        elif price >= t1:
            update_state(trade_id, price, "TARGET_1", "Target 1 hit")
        else:
            update_state(trade_id, price)
    print(
        "SIGNAL:",
        key,
        "| PRICE:", price,
        "| EMA9:", ema9,
        "| EMA20:", ema20,
        "| MOM:", mom,
        "| MARKET:", market,
        "| SIGNAL:", signal,
    )


def on_tick(key, data):
    price = data.get("ltp")
    ts = int(time.time() * 1000)

    if price is None or ts is None:
        return

    # Manage any open trade on every live tick.
    con = sqlite3.connect(DB_PATH)
    row = con.execute(
        "SELECT id,target_1,target_2,invalidation FROM trades WHERE symbol=? AND status NOT IN ('SELL','CLOSED') ORDER BY id DESC LIMIT 1",
        (key,)
    ).fetchone()
    con.close()

    if row:
        trade_id, t1, t2, invalidation = row
        if price <= invalidation:
            sell(trade_id, price, "Invalidation hit")
        elif price >= t2:
            sell(trade_id, price, "Target 2 hit")
        elif price >= t1:
            update_state(trade_id, price, "TARGET_1", "Target 1 hit")
        else:
            update_state(trade_id, price)

    before = len(candles.completed.get(key, []))
    candles.update(key, price, ts)
    after = len(candles.completed.get(key, []))

    # Analyse only when a minute candle has actually closed.
    if after > before:
        analyse(key)


if __name__ == "__main__":
    for key in INDICES.values(): preload_history(key)
    UpstoxLiveV3(on_tick=on_tick).connect()
