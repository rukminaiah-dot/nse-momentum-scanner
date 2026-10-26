"""Small, bounded JSON transport for Upstox read-only V3 candle endpoints."""
from functools import lru_cache
import json
import os
import re
import time
from pathlib import Path
from threading import Lock
from types import SimpleNamespace
from urllib.error import HTTPError
from urllib.parse import quote
from urllib.request import Request, urlopen

COOLDOWN_PATH = Path("/tmp/nse_history_cooldown")
MAX_HISTORY_BYTES = 8 * 1024 * 1024


class HistoryRequestError(RuntimeError):
    def __init__(self, status, retry_after=0, provider_code=None):
        self.status = status
        self.retry_after = retry_after
        self.provider_code = provider_code
        super().__init__(f'Upstox history HTTP {status}' + (f' [{provider_code}]' if provider_code else ''))


class HistoryApi:
    def __init__(self, token):
        self._token = token
        self._pace_lock = Lock()
        self._last_request = 0
        self._blocked_until = 0

    def _wait_for_slot(self):
        with self._pace_lock:
            try:
                shared_until = float(COOLDOWN_PATH.read_text())
            except (OSError, ValueError):
                shared_until = 0
            remaining = max(self._blocked_until, shared_until) - time.time()
            if remaining > 0:
                raise HistoryRequestError(429, remaining)
            pause = .3 - (time.monotonic() - self._last_request)
            if pause > 0:
                time.sleep(pause)
            self._last_request = time.monotonic()

    def _cool_down(self, headers, minimum=60):
        try:
            seconds = float(headers.get('Retry-After', 60))
            if not 0 < seconds < 86400:
                seconds = 60
        except (TypeError, ValueError):
            seconds = 60
        seconds = max(minimum, seconds)
        self._blocked_until = time.time() + seconds
        path = COOLDOWN_PATH
        tmp = path.with_name(path.name + '.' + str(os.getpid()) + '.tmp')
        try:
            tmp.write_text(str(self._blocked_until))
            tmp.replace(path)
        except OSError:
            pass
        return seconds

    def _get(self, segments):
        self._wait_for_slot()
        url = 'https://api.upstox.com/v3/historical-candle/' + '/'.join(
            quote(str(segment), safe='') for segment in segments)
        request = Request(url, headers={'Authorization':'Bearer ' + self._token,
                                       'Accept':'application/json'})
        try:
            with urlopen(request, timeout=20) as response:
                raw = response.read(MAX_HISTORY_BYTES + 1)
        except HTTPError as exc:
            # Retain only a strict provider error identifier; never log arbitrary bodies.
            provider_code = None
            try:
                error = json.loads(exc.read(16384))
                errors = error.get('errors', []) if isinstance(error, dict) else []
                code = errors[0].get('errorCode') if errors and isinstance(errors[0], dict) else None
                if isinstance(code, str) and re.fullmatch(r'UDAPI[0-9]{1,12}', code):
                    provider_code = code
            except (ValueError, TypeError, OSError):
                pass
            cooldown = self._cool_down(exc.headers, 300 if exc.code == 403 else 60) if exc.code in (403, 429) else 0
            raise HistoryRequestError(exc.code, cooldown, provider_code) from None
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
