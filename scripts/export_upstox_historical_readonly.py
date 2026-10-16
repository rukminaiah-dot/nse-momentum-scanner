"""Explicit, read-only Upstox 1-minute historical candle export.

Never imports scanner/trading/database modules. Dry-run unless --execute.
Keep output outside repository and CI artifacts; do not print credentials.
"""
import argparse
import csv
from datetime import date, datetime, time
from pathlib import Path
from zoneinfo import ZoneInfo

IST = ZoneInfo("Asia/Kolkata")


def normalize(rows):
    seen = set()
    output = []
    for row in rows:
        if len(row) < 6:
            raise ValueError("invalid OHLCV row")
        stamp = datetime.fromisoformat(str(row[0]))
        if stamp.tzinfo is None:
            raise ValueError("timestamp must contain timezone")
        stamp = stamp.astimezone(IST)
        if stamp.second or stamp.microsecond or not time(9, 15) <= stamp.time() < time(15, 30):
            raise ValueError("off-session or non-minute candle")
        values = [float(x) for x in row[1:6]]
        op, hi, lo, close, vol = values
        if not (lo <= min(op, close) <= max(op, close) <= hi) or vol < 0:
            raise ValueError("invalid OHLCV values")
        if stamp in seen:
            raise ValueError("duplicate minute")
        seen.add(stamp)
        output.append((stamp.isoformat(), op, hi, lo, close, vol))
    return sorted(output)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--instrument-key", required=True)
    parser.add_argument("--from-date", type=date.fromisoformat, required=True)
    parser.add_argument("--to-date", type=date.fromisoformat, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--execute", action="store_true", help="allow read-only API request")
    args = parser.parse_args()
    if not args.instrument_key.strip() or args.from_date > args.to_date or args.to_date >= datetime.now(IST).date():
        parser.error("instrument key and completed historical date range required")
    if args.output.exists():
        parser.error("output already exists; refusing overwrite")
    if not args.execute:
        print("DRY RUN: no API call or file write. Explicit --execute required.")
        return
    import os
    token = os.environ.get("UPSTOX_ACCESS_TOKEN")
    if not token:
        parser.error("UPSTOX_ACCESS_TOKEN is not configured")
    import upstox_client
    config = upstox_client.Configuration()
    config.access_token = token
    api = upstox_client.HistoryV3Api(upstox_client.ApiClient(config))
    try:
        response = api.get_historical_candle_data1(
            args.instrument_key, "minutes", "1", str(args.to_date), str(args.from_date))
    except Exception as exc:
        # The SDK exception may include response cookies, headers, HTML, or tokens.
        # Do not print the exception or traceback into GitHub Actions logs.
        status = getattr(exc, "status", None)
        if not isinstance(status, int) or status < 100 or status > 599:
            status = "unknown"
        raise SystemExit(
            f"Historical candle request failed (HTTP status: {status}). "
            "Response details suppressed to protect credentials and cookies. "
            "Check Upstox token validity, endpoint access, and network restrictions."
        ) from None
    candles = normalize(response.data.candles or [])
    if not candles:
        raise ValueError("API returned no candles")
    if any(not args.from_date <= datetime.fromisoformat(row[0]).date() <= args.to_date for row in candles):
        raise ValueError("API returned rows outside requested dates")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    # Exclusive creation and restrictive permissions. Caller must choose private storage.
    fd = os.open(args.output, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w", newline="", encoding="utf-8") as stream:
        writer = csv.writer(stream)
        writer.writerow(("timestamp", "open", "high", "low", "close", "volume"))
        writer.writerows(candles)
    print(f"Saved {len(candles)} read-only historical candles to a private local file.")


if __name__ == "__main__":
    main()
