"""Reuse one SDK client per process and bound every history HTTP request."""
from functools import lru_cache, partial


class BoundedHistoryApi:
    def __init__(self, api):
        self.api = api

    def __getattr__(self, name):
        method = getattr(self.api, name)
        if name in {'get_historical_candle_data1', 'get_intra_day_candle_data'}:
            return partial(method, _request_timeout=(5, 15))
        return method


@lru_cache(maxsize=1)
def history_api():
    import os
    import upstox_client
    config = upstox_client.Configuration()
    config.access_token = os.environ['UPSTOX_ACCESS_TOKEN']
    return BoundedHistoryApi(upstox_client.HistoryV3Api(upstox_client.ApiClient(config)))
