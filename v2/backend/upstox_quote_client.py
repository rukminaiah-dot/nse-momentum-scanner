"""Small Upstox full-quote client with a documented V3/V2 compatibility path."""

import json
import urllib.parse
import urllib.request
from collections.abc import Callable, Iterable
from typing import Any


QUOTE_ENDPOINTS = (
    ("/v3/market-quote/quotes", "Upstox Full Market Quotes V3"),
    ("/v2/market-quote/quotes", "Upstox Full Market Quotes V2"),
)


def fetch_full_quotes(
    keys: list[str],
    tokens: Iterable[str],
    *,
    request_json: Callable[[str, str, list[str]], dict[str, Any]] | None = None,
) -> tuple[dict[str, Any], str]:
    """Return quote data and API source, trying V2 if V3 rejects the request.

    Tokens are tried in configured order. No alternate market-data provider is
    used; the fallback only changes the Upstox API version.
    """
    if request_json is None:
        request_json = _request_json
    candidates = list(dict.fromkeys(token.strip() for token in tokens if token and token.strip()))
    if not candidates:
        raise ValueError("Upstox token not configured")

    last_error: Exception | None = None
    attempts: list[dict[str, Any]] = []
    for token in candidates:
        for path, source in QUOTE_ENDPOINTS:
            try:
                payload = request_json(path, token, keys)
                if (not isinstance(payload, dict)
                        or payload.get("status") != "success"
                        or not isinstance(payload.get("data"), dict)):
                    raise ValueError("Upstox quote response was not successful")
                return payload["data"], source
            except Exception as exc:
                last_error = exc
                status_code = getattr(exc, "code", None)
                attempts.append({
                    "api": "v3" if path.startswith("/v3/") else "v2",
                    "status_code": status_code if isinstance(status_code, int) else None,
                    "error": None if isinstance(status_code, int) else type(exc).__name__,
                })
    if last_error is not None:
        # Keep only non-sensitive endpoint and status diagnostics on the exception.
        # The API layer can report which compatibility paths were attempted
        # without including credentials, headers, or provider response bodies.
        last_error.upstox_attempts = attempts
    raise last_error or ValueError("Upstox quote request failed")


def _request_json(path: str, token: str, keys: list[str]) -> dict[str, Any]:
    query = urllib.parse.urlencode({"instrument_key": ",".join(keys)})
    request = urllib.request.Request(
        "https://api.upstox.com" + path + "?" + query,
        headers={"Authorization": "Bearer " + token, "Accept": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=5) as response:
        return json.loads(response.read().decode("utf-8"))
