"""Fail-closed preflight for a NONPRODUCTION live Upstox websocket test.

No network calls, no broker orders, no scanner imports, no secret values printed.
This preflight is deliberately separate from the real websocket integration test.
"""
import os
import sys


def check(environ=None):
    env = os.environ if environ is None else environ
    errors = []
    if env.get("FIX10_NONPRODUCTION_ACK") != "I_AM_IN_AN_ISOLATED_TEST":
        errors.append("isolated nonproduction acknowledgement missing")
    if env.get("ENABLE_VERIFIED_GAP_RECOVERY", "").strip().lower() in ("1", "true", "yes", "on"):
        errors.append("production recovery flag must not be enabled for preflight")
    if not env.get("UPSTOX_ACCESS_TOKEN", "").strip():
        errors.append("Upstox credential missing")
    if not env.get("FIX10_TEST_INSTRUMENT_KEY", "").strip():
        errors.append("authorized test instrument key missing")
    return errors


def main():
    errors = check()
    if errors:
        for message in errors:
            print("BLOCKED:", message, file=sys.stderr)
        return 2
    print("PASS: isolated test preflight configuration present")
    print("NOTE: no network connection or websocket validation was performed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
