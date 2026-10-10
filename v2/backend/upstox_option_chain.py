"""Read-only Upstox option-chain adapter using the existing access token.

No order APIs, token logging, inferred exchange timestamps, or fabricated lot sizes.
HTTP retrieval time is NOT proof that exchange quotes are fresh.
"""
import json
import os
from datetime import datetime, date
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

from .market_config import INDICES

BASE = "https://api.upstox.com/v2"
IST = ZoneInfo("Asia/Kolkata")


class OptionDataError(RuntimeError):
    pass


def _get(path, params, token):
    url = BASE + path + "?" + urlencode(params)
    request = Request(url, headers={
        "Authorization": "Bearer " + token,
        "Accept": "application/json",
    })
    try:
        with urlopen(request, timeout=8) as response:
            payload = json.load(response)
    except HTTPError as exc:
        # Do not expose response body; it may contain sensitive details.
        raise OptionDataError("UPSTOX_HTTP_" + str(exc.code)) from None
    except (URLError, TimeoutError, ValueError, OSError):
        raise OptionDataError("UPSTOX_DATA_UNAVAILABLE") from None
    if not isinstance(payload, dict) or payload.get("status") != "success" or not isinstance(payload.get("data"), list):
        raise OptionDataError("UPSTOX_INVALID_RESPONSE")
    return payload["data"]


def fetch_option_chain(index, expiry=None):
    """Fetch option-chain and matching contract metadata for one index.

    Does not rank contracts: Upstox chain response has no reliable per-quote
    exchange timestamp, so freshness cannot be asserted from fetch time.
    """
    if index not in ("NIFTY 50", "SENSEX"):
        raise ValueError("Unsupported index")
    if expiry is not None:
        try:
            if date.fromisoformat(expiry) < datetime.now(IST).date():
                raise ValueError("Expired option chain date")
        except (TypeError, ValueError):
            raise ValueError("Expiry must be a future YYYY-MM-DD date") from None
    token = os.environ.get("UPSTOX_ACCESS_TOKEN")
    if not token:
        return {"status": "NOT_CONNECTED", "reason": "UPSTOX_TOKEN_MISSING", "contracts": []}
    key = INDICES[index]
    metadata = _get("/option/contract", {"instrument_key": key}, token)
    available = sorted({str(row.get("expiry")) for row in metadata if isinstance(row, dict) and row.get("expiry")})
    if not available:
        return {"status": "NO_CONTRACTS", "reason": "NO_AVAILABLE_EXPIRIES", "contracts": []}
    chosen_expiry = expiry or next((d for d in available if d >= datetime.now(IST).date().isoformat()), None)
    if chosen_expiry not in available:
        return {"status": "NO_CONTRACTS", "reason": "EXPIRY_NOT_AVAILABLE", "contracts": []}
    chain = _get("/option/chain", {"instrument_key": key, "expiry_date": chosen_expiry}, token)
    lots = {
        c.get("instrument_key"): c.get("lot_size")
        for c in metadata if isinstance(c, dict) and c.get("instrument_key")
    }
    contracts = []
    for item in chain:
        if not isinstance(item, dict):
            continue
        for option_type, field in (("CE", "call_options"), ("PE", "put_options")):
            leg = item.get(field)
            if not isinstance(leg, dict):
                continue
            market = leg.get("market_data")
            if not isinstance(market, dict):
                continue
            instrument_key = leg.get("instrument_key")
            lot = lots.get(instrument_key)
            if not isinstance(lot, int) or isinstance(lot, bool) or lot <= 0:
                continue
            contracts.append({
                "type": option_type,
                "instrument_key": instrument_key,
                "strike": item.get("strike_price"),
                "expiry": chosen_expiry,
                "bid": market.get("bid_price"),
                "ask": market.get("ask_price"),
                "volume": market.get("volume"),
                "open_interest": market.get("oi"),
                "lot_size": lot,
                "ltp": market.get("ltp"),
                "option_greeks": leg.get("option_greeks"),
            })
    return {
        "status": "DATA_RETRIEVED_UNVERIFIED_FRESHNESS",
        "index": index,
        "expiry": chosen_expiry,
        "retrieved_at_ist": datetime.now(IST).isoformat(),
        "exchange_quote_time_ist": None,
        "contracts": contracts,
        "order_execution_enabled": False,
    }
