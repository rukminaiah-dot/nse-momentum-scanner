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


def close_stale_trades():
    con = sqlite3.connect(DB_PATH)
    con.execute("""UPDATE trades SET status='CLOSED', exit_reason='Session reset', exit_time=datetime('now','+5 hours','+30 minutes'), exit_price=current_price, realized_pnl=current_price-entry_price, realized_pnl_pct=((current_price-entry_price)/entry_price)*100 WHERE status NOT IN ('CLOSED','SELL') AND date(signal_time) < date('now','+5 hours','+30 minutes')""")
    con.commit()
    con.close()


def preload_history(key):
    config = upstox_client.Configuration()
    config.access_token = os.environ["UPSTOX_ACCESS_TOKEN"]
    api = upstox_client.HistoryV3Api(upstox_client.ApiClient(config))
    response = api.get_intra_day_candle_data(key, "minutes", 1)
    rows = response.data.candles or []
    if not rows:
        print("PRELOAD: no historical candles for", key)
        return

    loaded = []
    for row in reversed(rows[:20]):
        c = Candle(float(row[4]), 0)
        loaded.append(c)

    candles.completed[key] = loaded
    print("PRELOAD:", key, len(loaded), "candles")



def five_minute_trend(history):
    if len(history) < 20:
        return "NEUTRAL"

    closes = [c.close for c in history]
    five_closes = closes[-20::5]

    if len(five_closes) < 4:
        return "NEUTRAL"

    if five_closes[-1] > five_closes[-2] > five_closes[-3]:
        return "BULLISH"
    if five_closes[-1] < five_closes[-2] < five_closes[-3]:
        return "BEARISH"
    return "NEUTRAL"

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

    trend_5m = five_minute_trend(history)

    if signal == "BUY" and trend_5m != "BULLISH":
        signal = "HOLD"
    elif signal == "SELL" and trend_5m != "BEARISH":
        signal = "HOLD"

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
            con = sqlite3.connect(DB_PATH)
            status = con.execute("SELECT status FROM trades WHERE id=?", (trade_id,)).fetchone()
            con.close()
            update_state(trade_id, price, status[0] if status else "HOLD")
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
            # Preserve TARGET_1 once reached; only update its live price.
            con = sqlite3.connect(DB_PATH)
            status = con.execute("SELECT status FROM trades WHERE id=?", (trade_id,)).fetchone()
            con.close()
            update_state(trade_id, price, status[0] if status else "HOLD")

    before = len(candles.completed.get(key, []))
    candles.update(key, price, ts)
    after = len(candles.completed.get(key, []))

    # Analyse only when a minute candle has actually closed.
    if after > before:
        analyse(key)


if __name__ == "__main__":
    init_db()
    close_stale_trades()

    for key in list(INDICES.values()) + list(NIFTY_200.values()):
        try:
            preload_history(key)
            loaded = len(candles.completed.get(key, []))

            if loaded >= 20:
                print("PRELOAD READY:", key, loaded, "/20 candles")
            else:
                print("PRELOAD: live candle warmup for", key, "starting at", loaded, "/20")

        except Exception as e:
            print("PRELOAD ERROR:", key, str(e))
            print("PRELOAD: live candle warmup for", key)

    UpstoxLiveV3(on_tick=on_tick).connect()
