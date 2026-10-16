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
    parser.add_argument("--required-minute", action="append", default=[],
                        help="Exact completed IST minute to verify (YYYY-MM-DDTHH:MM); repeatable")
    args = parser.parse_args()
    # The intraday endpoint and validator cover the current IST session only.
    # Reject historical requests before touching credentials or the broker API.
    now_ist = datetime.now(ZoneInfo("Asia/Kolkata"))
    today_ist = now_ist.date()
    current_minute = now_ist.replace(second=0, microsecond=0, tzinfo=None)
    for raw_minute in args.required_minute:
        try:
            minute = datetime.fromisoformat(raw_minute)
        except ValueError:
            parser.error("--required-minute must use YYYY-MM-DDTHH:MM")
        if (minute.tzinfo is not None or minute.second or minute.microsecond
                or minute.date() != today_ist or minute >= current_minute):
            parser.error("--required-minute must be a completed minute from today in IST; "
                         "historical dates require a separate historical-candle endpoint")
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
        requested = []
        for raw_minute in args.required_minute:
            minute = datetime.fromisoformat(raw_minute)
            if minute.tzinfo is not None or minute.second or minute.microsecond:
                raise ValueError("required minute must be a naive IST minute")
            requested.append(minute)
        for minute in requested:
            print("required_minute:", minute.isoformat(timespec="minutes"),
                  "VERIFIED" if minute in verified else "NOT_VERIFIED")
        if requested and any(minute not in verified for minute in requested):
            print("INCONCLUSIVE: one or more requested minutes lack verified broker candles")
            return 3
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
        rows_by_minute = {}
        for raw in rows:
            stamp = datetime.fromisoformat(str(raw[0]))
            if stamp.tzinfo is not None:
                minute = stamp.astimezone(ZoneInfo("Asia/Kolkata")).replace(tzinfo=None)
                rows_by_minute[minute] = raw
        # Exercise the actual asynchronous worker with the already fetched
        # broker response. No second API request and no shared scanner state.
        from v2.backend.gap_recovery_worker import GapRecoveryWorker
        state = [original]
        active = missing + timedelta(minutes=1)
        def isolated_snapshot(_key):
            return list(state), active
        def isolated_merge(_key, candidates, expected_active):
            nonlocal state
            state, additions = merge_verified_missing(
                state, candidates, active_minute=expected_active)
            return len(additions)
        worker = GapRecoveryWorker(
            lambda _key: [rows_by_minute[missing]],
            isolated_snapshot, isolated_merge,
            cooldown=120, max_pending=1, min_request_spacing=0.001)
        if not worker.request("ISOLATED_TEST"):
            raise ValueError("isolated recovery request rejected")
        worker.join(timeout=5)
        stats = worker.status()
        if (stats["pending"] != 0 or stats["failed"] != 0
                or stats["completed"] != 1 or stats["verified_insertions"] != 1
                or len(state) != 2):
            raise ValueError("isolated worker did not restore exactly one gap")
        print("PASS: real-candle asynchronous recovery worker verified")
        print("PASS: authenticated read-only response parsed and validated")
        print("PASS: real-candle in-memory gap insertion and idempotence verified")
        return 0
    except Exception as exc:
        # Avoid printing exception text: SDK errors may include request metadata.
        print("FAIL: read-only Upstox probe:", type(exc).__name__, file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
