"""Manual, isolated, read-only Upstox websocket smoke test.

Optionally exercises read-only gap recovery. No scanner imports, persistence, or orders.
Requires explicit nonproduction acknowledgement and an authorized instrument.
Prints only connection/tick counters, never raw messages or credentials.
"""
import os
import sys
import threading
import time

from preflight_upstox_websocket import check
from isolated_live_tick_candles import extract_tick, IsolatedTickCandles
from isolated_stream_recovery import IsolatedStreamRecovery
from isolated_upstox_history import make_historical_fetch

# After the first fresh tick, keep listening for a natural minute jump.
RECOVERY_OBSERVE_SECONDS = 90


def has_instrument_tick(payload, instrument):
    """Only validated instrument trade ticks count as websocket evidence."""
    return extract_tick(payload, instrument) is not None

def main():
    failures = check()
    if failures:
        for failure in failures:
            print("BLOCKED:", failure, file=sys.stderr)
        return 2

    # Fail closed: only run when the operator explicitly authorizes a short
    # read-only live subscription. No implicit run in CI or production.
    if os.environ.get("FIX10_LIVE_STREAM_ACK") != "READ_ONLY_STREAM_TEST":
        print("BLOCKED: live stream acknowledgement missing", file=sys.stderr)
        return 2
    recovery_ack = os.environ.get("FIX10_ISOLATED_RECOVERY_ACK")
    if recovery_ack not in (None, "", "READ_ONLY_HISTORY"):
        print("BLOCKED: unrecognized recovery acknowledgement", file=sys.stderr)
        return 2

    try:
        import upstox_client
        config = upstox_client.Configuration()
        config.access_token = os.environ["UPSTOX_ACCESS_TOKEN"]
        api_client = upstox_client.ApiClient(config)
        instrument = os.environ["FIX10_TEST_INSTRUMENT_KEY"]
        streamer = upstox_client.MarketDataStreamerV3(api_client, [instrument], "ltpc")
        recovery_mode = recovery_ack == "READ_ONLY_HISTORY"
        if recovery_mode:
            historical = upstox_client.HistoryV3Api(api_client)
            bridge = IsolatedStreamRecovery(instrument, make_historical_fetch(historical, instrument))
    except Exception as exc:
        print("BLOCKED: SDK initialization:", type(exc).__name__, file=sys.stderr)
        return 2

    opened = threading.Event()
    ready = threading.Event()
    seen = threading.Event()
    gap_seen = threading.Event()
    errored = threading.Event()
    counts = {"messages": 0, "stale": 0}
    state_lock = threading.Lock()
    isolated = bridge.candles if recovery_mode else IsolatedTickCandles(instrument)

    def on_open(*_args):
        opened.set()
        ready.set()

    def on_message(*args):
        # An open socket, heartbeat, or subscription acknowledgement is NOT
        # evidence of market ticks. Require an instrument feed with LTPC.
        payload = args[0] if args else None
        tick = extract_tick(payload, instrument)
        if tick is None:
            return
        # A replayed/cached tick is not evidence of a LIVE market feed.
        # Upstox ltt is exchange epoch milliseconds.
        if abs(int(time.time() * 1000) - tick[1]) > 120_000:
            with state_lock:
                counts["stale"] += 1
            return
        try:
            if not (bridge.on_message(payload) if recovery_mode else isolated.on_message(payload)):
                return
            if recovery_mode and bridge.gap_requests:
                gap_seen.set()
        except Exception:
            # Callback errors must not be mistaken for successful integration.
            errored.set()
            ready.set()
            return
        with state_lock:
            counts["messages"] += 1
        seen.set()

    def on_error(*_args):
        errored.set()
        ready.set()

    streamer.on("open", on_open)
    streamer.on("message", on_message)
    streamer.on("error", on_error)

    # A daemonized connector prevents an SDK blocking connect from hanging
    # this disposable smoke process. Exit is always bounded.
    def connect_safely():
        try:
            streamer.connect()
        except Exception:
            errored.set()
            ready.set()

    connector = threading.Thread(target=connect_safely, daemon=True)
    connector.start()
    try:
        ready.wait(timeout=15)
        if not opened.is_set():
            if errored.is_set():
                print("INCONCLUSIVE: websocket connection failed")
                return 3
            print("INCONCLUSIVE: websocket did not open within timeout")
            return 3
        if not seen.wait(timeout=45):
            if errored.is_set():
                print("INCONCLUSIVE: websocket reported an error")
                return 3
            print("INCONCLUSIVE: no fresh live tick observed within timeout")
            return 3
        if errored.is_set():
            print("INCONCLUSIVE: websocket reported an error")
            return 3
        history, active = isolated.manager.recovery_snapshot(instrument)
        if active is None:
            print("INCONCLUSIVE: tick did not enter isolated candle manager")
            return 3
        print("PASS: fresh websocket tick entered isolated candle manager")
        with state_lock:
            print("message_count:", counts["messages"])
            print("stale_ticks_ignored:", counts["stale"])
        print("completed_candles:", len(history))
        if recovery_mode:
            # The first live tick alone cannot establish a minute gap. Keep
            # the subscription active for a bounded observation window.
            deadline = time.monotonic() + RECOVERY_OBSERVE_SECONDS
            while (not gap_seen.is_set() and not errored.is_set()
                   and time.monotonic() < deadline):
                gap_seen.wait(timeout=min(1, max(0, deadline - time.monotonic())))
            if errored.is_set():
                print("INCONCLUSIVE: websocket error during recovery observation")
                return 3
            # Do not claim historical recovery succeeded merely because ticks
            # arrived: a naturally occurring minute gap may never occur.
            # Give an already scheduled off-feed worker a bounded chance to
            # finish before reporting acceptance. Never wait on feed callbacks.
            bridge.worker.join(timeout=5)
            stats = bridge.worker.status()
            if errored.is_set():
                print("INCONCLUSIVE: websocket error during historical recovery")
                return 3
            print("gap_requests:", bridge.gap_requests)
            print("recovery_completed:", stats["completed"])
            print("verified_insertions:", stats["verified_insertions"])
            print("recovery_failed:", stats["failed"])
            if bridge.gap_requests == 0:
                print("INCONCLUSIVE: no live minute gap observed; recovery unverified")
            elif stats["pending"]:
                print("INCONCLUSIVE: historical recovery still pending")
            elif stats["failed"]:
                print("INCONCLUSIVE: historical recovery failed")
            elif stats["verified_insertions"] == 0:
                print("INCONCLUSIVE: no missing broker candle verified")
            else:
                print("PASS: live gap scheduled and verified historical candle inserted")
                return 0
            return 3
        else:
            print("NOTE: recovery worker was not invoked; integration gate remains pending")
        return 0
    finally:
        # SDK disconnect can block on network teardown. Never let an
        # inconclusive disposable probe hang indefinitely during cleanup.
        def disconnect_safely():
            try:
                streamer.disconnect()
            except Exception:
                pass
        cleanup = threading.Thread(target=disconnect_safely, daemon=True)
        cleanup.start()
        cleanup.join(timeout=3)
        if cleanup.is_alive():
            print("WARNING: websocket disconnect exceeded cleanup timeout")


if __name__ == "__main__":
    sys.exit(main())
