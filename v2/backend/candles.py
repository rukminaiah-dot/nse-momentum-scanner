class Candle:
    def __init__(self, price, volume=0):
        self.open = self.high = self.low = self.close = float(price)
        self.volume = float(volume)

    def update(self, price, volume=0):
        price = float(price)
        self.high = max(self.high, price)
        self.low = min(self.low, price)
        self.close = price
        self.volume += float(volume)

print("V2_CANDLE_ENGINE_OK")
