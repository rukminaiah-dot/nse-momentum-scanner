"""Read-only authenticated Upstox intraday response probe.

Run manually in a NON-PRODUCTION environment with a temporary access token.
Never prints credentials, instrument keys, prices, volumes, or raw responses.
Never submits orders, starts the scanner, or changes candle state.
"""
import argparse
import os
import sys
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo


def main():
    parser = argparse.ArgumentParser(description="Read-only Upstox intraday verification")
    parser.add_argument("--instrument-key", required=True,
                        help="Upstox instrument key for an authorized test instrument")
    args = parser.parse_args()
    token = os.getenv("UPSTOX_ACCESS_TOKEN")
    if not token:
        print("FAIL: UPSTOX_ACCESS_TOKEN is not set", file=sys.stderr)
        return 2

    try:
        import upstox_client
        from v2.backend.verified_gap_recovery import validated_completed_rows
        config = upstox_client.Configuration()
        config.access_token = token
        api = upstox_client.HistoryV3Api(upstox_client.ApiClient(config))
        response = api.get_intra_day_candle_data(args.instrument_key, "minutes", "1")
        if response is None or getattr(response, "data", None) is None:
            raise ValueError("missing Upstox response data")
        rows = response.data.candles
        if rows is None or not isinstance(rows, (list, tuple)):
            raise ValueError("missing or invalid candle collection")
        verified = validated_completed_rows(rows, datetime.now(ZoneInfo("Asia/Kolkata")))
        print("returned_rows:", len(rows))
        print("verified_completed_same_day_rows:", len(verified))
        if not verified:
            print("INCONCLUSIVE: no verified completed same-day bars; retry during an active market session")
            return 3
        # Isolated in-memory gap: no scanner, database, or orders.
        from v2.backend.verified_gap_recovery import merge_verified_missing
        minutes = sorted(verified)
        pair = next(((a, b) for a, b in zip(minutes, minutes[1:])
                     if b - a == timedelta(minutes=1)), None)
        if pair is None:
            print("INCONCLUSIVE: no adjacent verified candles for in-memory gap test")
            return 3
        earlier, missing = pair
        original = verified[earlier]
        recovered = {missing: verified[missing]}
        restored, inserted = merge_verified_missing(
            [original], recovered, active_minute=missing + timedelta(minutes=1))
        if (inserted != [missing] or len(restored) != 2
                or restored[0] is not original or restored[1] is not verified[missing]):
            raise ValueError("in-memory gap merge did not restore expected candle")
        repeated, inserted_again = merge_verified_missing(
            restored, recovered, active_minute=missing + timedelta(minutes=1))
        if inserted_again or len(repeated) != 2 or repeated[0] is not original:
            raise ValueError("in-memory merge not idempotent")
        print("PASS: authenticated read-only response parsed and validated")
        print("PASS: real-candle in-memory gap insertion and idempotence verified")
        return 0
    except Exception as exc:
        # Avoid printing exception text: SDK errors may include request metadata.
        print("FAIL: read-only Upstox probe:", type(exc).__name__, file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
