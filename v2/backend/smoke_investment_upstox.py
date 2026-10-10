"""Read-only Upstox historical API smoke check.

Run in an isolated environment with UPSTOX_ACCESS_TOKEN configured.
Prints no tokens, URLs, or prices; never places orders.
Exit code is nonzero unless all ten stocks return fresh historical candles.
"""
import sys
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from v2.backend.investment import SYMBOLS, analyze

def main():
    now = datetime.now(ZoneInfo("Asia/Kolkata"))
    end = now.date()
    if now.weekday() < 5 and (now.hour, now.minute) < (15, 45):
        end -= timedelta(days=1)
    while end.weekday() >= 5:
        end -= timedelta(days=1)
    passed = 0
    for symbol in SYMBOLS:
        try:
            result = analyze(symbol, end)
            assert result["quote_type"] == "DAILY_CLOSE_NOT_LIVE"
            assert result["price"] > 0
            assert result["weekly_ema20"] is not None
            print(f"{symbol}: PASS (daily close available, no price printed)")
            passed += 1
        except Exception as exc:
            print(f"{symbol}: FAIL ({type(exc).__name__})")
    print(f"Historical-data checks: {passed}/{len(SYMBOLS)}")
    return 0 if passed == len(SYMBOLS) else 1

if __name__ == "__main__":
    sys.exit(main())
