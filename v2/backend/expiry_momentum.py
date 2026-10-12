from datetime import datetime, time
from zoneinfo import ZoneInfo

IST = ZoneInfo("Asia/Kolkata")
WATCH_START = time(9, 15)
WATCH_END = time(15, 20)

SUPPORTED_INDICES = ("NIFTY 50", "SENSEX")


def expiry_watch_status(index_name, now=None):
    """Daily research observation; holidays must be checked separately."""
    now = now or datetime.now(IST)
    if index_name not in SUPPORTED_INDICES:
        return "UNSUPPORTED"
    if now.weekday() >= 5:
        return "MARKET_CLOSED"
    if not WATCH_START <= now.time() <= WATCH_END:
        return "OUTSIDE_WINDOW"
    return "WATCH"


if __name__ == "__main__":
    for index in SUPPORTED_INDICES:
        print(index, expiry_watch_status(index))
