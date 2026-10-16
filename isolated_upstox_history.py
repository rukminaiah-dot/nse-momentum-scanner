"""Read-only Upstox V3 intraday adapter for isolated Fix 10 tests.

The caller MUST pass this callable to GapRecoveryWorker; never call it from
a websocket callback. No order APIs or production scanner imports.
"""


def make_historical_fetch(api, instrument):
    if not instrument:
        raise ValueError("test instrument required")

    def fetch(key):
        if key != instrument:
            raise ValueError("instrument mismatch")
        response = api.get_intra_day_candle_data(instrument, "minutes", "1")
        data = getattr(response, "data", None)
        rows = getattr(data, "candles", None)
        if not isinstance(rows, (list, tuple)):
            raise ValueError("invalid Upstox intraday response")
        return rows

    return fetch
