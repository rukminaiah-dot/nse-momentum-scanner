"""Small, bounded JSON transport for Upstox read-only V3 candle endpoints."""
from functools import lru_cache
import json
from types import SimpleNamespace
from urllib.error import HTTPError
from urllib.parse import quote
from urllib.request import Request, urlopen

MAX_HISTORY_BYTES = 8 * 1024 * 1024


class HistoryRequestError(RuntimeError):
    def __init__(self, status):
        self.status = status
        super().__init__(f'Upstox history HTTP {status}')


class HistoryApi:
    def __init__(self, token):
        self._token = token

    def _get(self, segments):
        url = 'https://api.upstox.com/v3/historical-candle/' + '/'.join(
            quote(str(segment), safe='') for segment in segments)
        request = Request(url, headers={'Authorization':'Bearer ' + self._token,
                                       'Accept':'application/json'})
        try:
            with urlopen(request, timeout=20) as response:
                raw = response.read(MAX_HISTORY_BYTES + 1)
        except HTTPError as exc:
            raise HistoryRequestError(exc.code) from None
        if len(raw) > MAX_HISTORY_BYTES:
            raise ValueError('history response exceeds size limit')
        payload = json.loads(raw)
        data = payload.get('data') if isinstance(payload, dict) else None
        candles = data.get('candles') if isinstance(data, dict) else None
        if not isinstance(candles, list):
            raise ValueError('invalid history candle response')
        return SimpleNamespace(data=SimpleNamespace(candles=candles))

    def get_historical_candle_data1(self, key, unit, interval, to_date, from_date):
        return self._get((key, unit, interval, to_date, from_date))

    def get_intra_day_candle_data(self, key, unit, interval):
        return self._get(('intraday', key, unit, interval))


@lru_cache(maxsize=1)
def history_api():
    import os
    return HistoryApi(os.environ['UPSTOX_ACCESS_TOKEN'])
