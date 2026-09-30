import os
import json
import gzip
import urllib.parse
import urllib.request
import pandas as pd

def _token():

    token = os.environ.get("UPSTOX_ACCESS_TOKEN", "").strip()

    if not token:

        raise RuntimeError("UPSTOX_ACCESS_TOKEN is not set")

    return token

USER_AGENT = "Mozilla/5.0"

def _headers():

    return {"Authorization": "Bearer " + _token(), "Accept": "application/json", "User-Agent": USER_AGENT}

def _get_json(url):

    request = urllib.request.Request(url, headers=_headers())

    with urllib.request.urlopen(request, timeout=15) as response:

        return json.loads(response.read().decode("utf-8"))

def daily_candles(instrument_key, from_date, to_date):

    key = urllib.parse.quote(instrument_key, safe="")

    url = f"https://api.upstox.com/v3/historical-candle/{key}/days/1/{to_date}/{from_date}"

    return _get_json(url)["data"]["candles"]

def candles_frame(candles):

    rows = sorted(candles, key=lambda x: x[0])

    return pd.DataFrame(rows, columns=["Timestamp","Open","High","Low","Close","Volume","OpenInterest"])

NSE_INSTRUMENTS_URL = "https://assets.upstox.com/market-quote/instruments/exchange/NSE.json.gz"

def load_nse_instruments():

    request = urllib.request.Request(NSE_INSTRUMENTS_URL, headers={"User-Agent": USER_AGENT})

    with urllib.request.urlopen(request, timeout=30) as response:

        return json.loads(gzip.decompress(response.read()))

def instrument_map():

    return {i["trading_symbol"]: i["instrument_key"] for i in load_nse_instruments() if i.get("instrument_type") in ("EQ", "BE")}
