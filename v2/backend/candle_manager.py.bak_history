from datetime import datetime
from .candles import Candle

class CandleManager:
    def __init__(self):
        self.current = {}
        self.completed = {}

    def minute_key(self, ts):
        return datetime.fromtimestamp(float(ts) / 1000).replace(second=0, microsecond=0)

    def update(self, key, price, ts, volume=0):
        minute = self.minute_key(ts)
        item = self.current.get(key)

        if item is None or item["minute"] != minute:
            if item:
                closed = item["candle"]
                self.completed.setdefault(key, []).append(closed)
                print("CANDLE_CLOSED", key, closed.__dict__)
            self.current[key] = {"minute": minute, "candle": Candle(price, volume)}
            return closed if item else None
        else:
            item["candle"].update(price, volume)
            return None
