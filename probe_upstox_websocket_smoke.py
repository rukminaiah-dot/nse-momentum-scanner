"""Manual, isolated, read-only Upstox websocket smoke test.

NOT a gap-recovery integration test. No scanner imports, persistence, or orders.
Requires explicit nonproduction acknowledgement and an authorized instrument.
Prints only connection/tick counters, never raw messages or credentials.
"""
import os
import sys
import threading

from preflight_upstox_websocket import check


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

    try:
        import upstox_client
        config = upstox_client.Configuration()
        config.access_token = os.environ["UPSTOX_ACCESS_TOKEN"]
        api_client = upstox_client.ApiClient(config)
        instrument = os.environ["FIX10_TEST_INSTRUMENT_KEY"]
        streamer = upstox_client.MarketDataStreamerV3(api_client, [instrument], "ltpc")
    except Exception as exc:
        print("BLOCKED: SDK initialization:", type(exc).__name__, file=sys.stderr)
        return 2

    opened = threading.Event()
    ready = threading.Event()
    seen = threading.Event()
    errored = threading.Event()
    counts = {"messages": 0}

    def on_open(*_args):
        opened.set()
        ready.set()

    def on_message(*_args):
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
            print("INCONCLUSIVE: no live message observed within timeout")
            return 3
        if errored.is_set():
            print("INCONCLUSIVE: websocket reported an error")
            return 3
        print("PASS: websocket opened and received live message(s)")
        print("message_count:", counts["messages"])
        print("NOTE: recovery worker was not invoked; integration gate remains pending")
        return 0
    finally:
        try:
            streamer.disconnect()
        except Exception:
            pass


if __name__ == "__main__":
    sys.exit(main())
